import re
import json
from pathlib import Path
from typing import Collection, Optional

from defame.common import Report, Label, Claim, Action, Prompt, Content, logger
from defame.common.label import DEFAULT_LABEL_DEFINITIONS
from defame.common.misc import WebSource
from defame.common.results import Result
from defame.utils.parsing import (remove_non_symbols, extract_last_code_span, read_md_file,
                                  find_code_span, extract_last_paragraph, extract_last_code_block,
                                  strip_string, remove_code_blocks)

SYMBOL = 'Check-worthy'
NOT_SYMBOL = 'Unimportant'


class JudgePrompt(Prompt):
    template_file_path = "defame/prompts/judge.md"
    name = "JudgePrompt"
    retry_instruction = ("(Do not forget to choose one option from Decision Options "
                         "and enclose it in backticks like `this`)") 

    def __init__(self, doc: Report,
                 classes: Collection[Label],
                 class_definitions: dict[Label, str] = None,
                 extra_rules: str = None):
        if class_definitions is None:
            class_definitions = DEFAULT_LABEL_DEFINITIONS
        self.classes = classes
        class_str = '\n'.join([f"* `{cls.value}`: {remove_non_symbols(class_definitions[cls])}"
                               for cls in classes])
        placeholder_targets = {
            "[DOC]": str(doc),
            "[CLASSES]": class_str,
            "[EXTRA_RULES]": "" if extra_rules is None else remove_non_symbols(extra_rules),
        }
        super().__init__(placeholder_targets)

    def extract(self, response: str) -> dict | str | None:
        verdict = extract_verdict(response, classes=self.classes)
        # Add confidence scores here
       # confidence = extract_confidence_scores_json(response, classes=self.classes)
        if verdict is None:
            return None
        else:
            return dict(verdict=verdict, 
                      #  confidence = confidence, # Add confidence scores here
                        response=response)


class DecontextualizePrompt(Prompt):
    template_file_path = "defame/prompts/decontextualize.md"
    name = "DecontextualizePrompt"

    def __init__(self, claim: Claim):
        placeholder_targets = {
            "[ATOMIC_FACT]": claim.text,
            "[CONTEXT]": claim.original_context.text,  # TODO: improve this, add images etc.
        }
        super().__init__(placeholder_targets)


class FilterCheckWorthyPrompt(Prompt):
    name = "FilterCheckWorthyPrompt"

    def __init__(self, claim: Claim, filter_method: str = "default"):
        assert (filter_method in ["default", "custom"])
        placeholder_targets = {  # re-implement this
            "[SYMBOL]": SYMBOL,
            "[NOT_SYMBOL]": NOT_SYMBOL,
            "[ATOMIC_FACT]": claim,
            "[CONTEXT]": claim.original_context,
        }
        if filter_method == "custom":
            self.template_file_path = "defame/prompts/custom_checkworthy.md"
        else:
            self.template_file_path = "defame/prompts/default_checkworthy.md"
        super().__init__(placeholder_targets)


class SummarizeResultPrompt(Prompt):
    template_file_path = "defame/prompts/summarize_result.md"
    name = "SummarizeResultPrompt"

    def __init__(self, search_result: WebSource, doc: Report):
        placeholder_targets = {
            "[SEARCH_RESULT]": str(search_result),
            "[DOC]": str(doc),
        }
        super().__init__(placeholder_targets)


class SummarizeManipulationResultPrompt(Prompt):
    template_file_path = "defame/prompts/summarize_manipulation_result.md"
    name = "SummarizeManipulationResultPrompt"

    def __init__(self, manipulation_result: Result):
        placeholder_targets = {
            "[MANIPULATION_RESULT]": str(manipulation_result),
        }
        super().__init__(placeholder_targets)


class SummarizeDocPrompt(Prompt):
    template_file_path = "defame/prompts/summarize_doc.md"
    name = "SummarizeDocPrompt"

    def __init__(self, doc: Report):
        super().__init__({"[DOC]": doc})


class PlanPrompt(Prompt):
    template_file_path = "defame/prompts/plan.md"
    name = "PlanPrompt"

    def __init__(self, doc: Report,
                 valid_actions: list[type[Action]],
                 extra_rules: str = None,
                 all_actions: bool = False):
        self.context = doc.claim.original_context
        valid_action_str = "\n\n".join([f"* `{a.name}`\n"
                                        f"   * Description: {remove_non_symbols(a.description)}\n"
                                        f"   * How to use: {remove_non_symbols(a.how_to)}\n"
                                        f"   * Format: {a.format}" for a in valid_actions])
        extra_rules = "" if extra_rules is None else remove_non_symbols(extra_rules)
        if all_actions:
            extra_rules = "Very Important: No need to be frugal. Choose all available actions at least once."

        placeholder_targets = {
            "[DOC]": doc,
            "[VALID_ACTIONS]": valid_action_str,
            "[EXEMPLARS]": load_exemplars(valid_actions),
            "[EXTRA_RULES]": extra_rules,
        }
        super().__init__(placeholder_targets)

    def extract(self, response: str) -> dict:
        # TODO: Prevent the following from happening at all.
        # It may accidentally happen that the LLM generated "<image:k>" in its response (because it was
        # included as an example in the prompt).
        pattern = re.compile(r'<image:k>')
        matches = pattern.findall(response)

        if matches:
            # Replace "<image:k>" with the reference to the claim's image by assuming that the first image
            # is tha claim image.
            if self.images:
                claim_image_ref = self.images[
                    0].reference  # Be careful that the Plan Prompt always has the Claim image first before any other image!
                response = pattern.sub(claim_image_ref, response)
                print(f"WARNING: <image:k> was replaced by {claim_image_ref} to generate response: {response}")

        actions = extract_actions(response)
        reasoning = extract_reasoning(response)
        return dict(
            actions=actions,
            reasoning=reasoning,
            response=response,
        )


class PoseQuestionsPrompt(Prompt):
    name = "PoseQuestionsPrompt"

    def __init__(self, doc: Report, n_questions: int = 10, interpret: bool = True):
        placeholder_targets = {
            "[CLAIM]": doc.claim,
            "[N_QUESTIONS]": n_questions
        }
        if interpret:
            self.template_file_path = "defame/prompts/pose_questions.md"
        else:
            self.template_file_path = "defame/prompts/pose_questions_no_interpretation.md"
        super().__init__(placeholder_targets)

    def extract(self, response: str) -> dict:
        questions = find_code_span(response)
        return dict(
            questions=questions,
            response=response,
        )


class ProposeQueries(Prompt):
    """Used to generate queries to answer AVeriTeC questions."""
    template_file_path = "defame/prompts/propose_queries.md"
    name = "ProposeQueries"

    def __init__(self, question: str, doc: Report):
        placeholder_targets = {
            "[DOC]": doc,
            "[QUESTION]": question,
        }
        super().__init__(placeholder_targets)

    def extract(self, response: str) -> dict:
        queries = extract_queries(response)
        return dict(
            queries=queries,
            response=response,
        )


class ProposeQuerySimple(Prompt):
    """Used to generate queries to answer AVeriTeC questions."""
    template_file_path = "defame/prompts/propose_query_simple.md"
    name = "ProposeQuerySimple"

    def __init__(self, question: str):
        placeholder_targets = {
            "[QUESTION]": question,
        }
        super().__init__(placeholder_targets)

    def extract(self, response: str) -> dict:
        queries = extract_queries(response)
        return dict(
            queries=queries,
            response=response,
        )


class ProposeQueriesNoQuestions(Prompt):
    """Used to generate queries to answer AVeriTeC questions."""
    template_file_path = "defame/prompts/propose_queries_no_questions.md"
    name = "ProposeQueriesNoQuestions"

    def __init__(self, doc: Report):
        placeholder_targets = {
            "[DOC]": doc,
        }
        super().__init__(placeholder_targets)

    def extract(self, response: str) -> dict:
        queries = extract_queries(response)
        return dict(
            queries=queries,
            response=response,
        )


class AnswerCollectively(Prompt):
    """Used to generate answers to the AVeriTeC questions."""
    template_file_path = "defame/prompts/answer_question_collectively.md"
    name = "AnswerCollectively"

    def __init__(self, question: str, results: list[WebSource], doc: Report):
        result_strings = [f"## Result `{i}`\n{str(result)}" for i, result in enumerate(results)]
        results_str = "\n\n".join(result_strings)

        placeholder_targets = {
            "[DOC]": doc,
            "[QUESTION]": question,
            "[RESULTS]": results_str,
        }
        super().__init__(placeholder_targets)

    def extract(self, response: str) -> dict:
        """Extract result ID and answer to the question from response"""
        answered = "NONE" not in response and "None" not in response

        out = dict(
            answered=answered,
            response=response,
        )

        if answered:
            result_id = extract_last_code_span(response)
            if result_id != "":
                result_id = int(result_id)
                answer = extract_last_paragraph(response)
                out.update(dict(
                    answer=answer,
                    result_id=result_id,
                ))

        return out


class AnswerQuestion(Prompt):
    """Used to generate answers to the AVeriTeC questions."""
    template_file_path = "defame/prompts/answer_question.md"
    name = "AnswerQuestion"

    def __init__(self, question: str, result: WebSource, doc: Report):
        placeholder_targets = {
            "[DOC]": doc,
            "[QUESTION]": question,
            "[RESULT]": result,
        }
        super().__init__(placeholder_targets)

    def extract(self, response: str) -> dict:
        """Extract result ID and answer to the question from response"""
        answered = "NONE" not in response and "None" not in response

        out = dict(
            answered=answered,
            response=response,
        )

        if answered:
            answer = extract_last_paragraph(response)
            out.update(dict(answer=answer))

        return out


class AnswerQuestionNoEvidence(Prompt):
    """Used to generate answers to the AVeriTeC questions."""
    template_file_path = "defame/prompts/answer_question_no_evidence.md"
    name = "AnswerQuestionNoEvidence"

    def __init__(self, question: str, doc: Report):
        placeholder_targets = {
            "[DOC]": doc,
            "[QUESTION]": question,
        }
        super().__init__(placeholder_targets)


class DevelopPrompt(Prompt):
    template_file_path = "defame/prompts/develop.md"
    name = "DevelopPrompt"

    def __init__(self, doc: Report):
        placeholder_targets = {"[DOC]": doc}
        super().__init__(placeholder_targets)


class InterpretPrompt(Prompt):
    template_file_path = "defame/prompts/interpret.md"
    name = "InterpretPrompt"

    def __init__(self, content: Content, guidelines: str = ''):
        if guidelines:
            guidelines = "# Guidelines\n" + guidelines
        placeholder_targets = {
            "[CONTENT]": content,
            "[GUIDELINES]": guidelines,
        }
        super().__init__(placeholder_targets)


class JudgeNaively(Prompt):
    template_file_path = "defame/prompts/judge_naive.md"
    name = "JudgeNaively"

    def __init__(self, claim: Claim,
                 classes: Collection[Label],
                 class_definitions: dict[Label, str] = None):
        self.classes = classes
        if class_definitions is None:
            class_definitions = DEFAULT_LABEL_DEFINITIONS
        class_str = '\n'.join([f"* `{cls.value}`: {remove_non_symbols(class_definitions[cls])}"
                               for cls in classes])
        placeholder_targets = {
            "[CLAIM]": claim,
            "[CLASSES]": class_str,
        }
        super().__init__(placeholder_targets)

    def extract(self, response: str) -> dict:
        verdict = extract_verdict(response, classes=self.classes)
        return dict(verdict=verdict, response=response)


class JudgeMinimal(JudgeNaively):
    template_file_path = "defame/prompts/judge_minimal.md"
    name = "JudgeMinimal"


class InitializePrompt(Prompt):
    template_file_path = "defame/prompts/initialize.md"
    name = "InitializePrompt"

    def __init__(self, claim: Claim):
        placeholder_targets = {
            "[CLAIM]": claim,
        }
        super().__init__(placeholder_targets)


def load_exemplars(valid_actions: list[type[Action]]) -> str:
    exemplars_dir = Path("defame/prompts/plan_exemplars")
    exemplar_paths = []
    for a in valid_actions:
        exemplar_path = exemplars_dir / f"{a.name}.md"
        if exemplar_path.exists():
            exemplar_paths.append(exemplar_path)

    if len(exemplar_paths) == 0:
        return read_md_file(exemplars_dir / "default.md")
    else:
        return "\n\n".join([read_md_file(path) for path in exemplar_paths])


def parse_single_action(raw_action: str) -> Optional[Action]:
    from defame.tools import ACTION_REGISTRY

    if not raw_action:
        return None
    elif raw_action[0] == '"':
        raw_action = raw_action[1:]

    try:
        match = re.match(r'(\w+)\((.*)\)', raw_action)
        if match:
            action_name, arguments = match.groups()
            arguments = arguments.strip()
        else:
            match = re.search(r'"(.*?)"', raw_action)
            arguments = f'"{match.group(1)}"' if match else f'"{raw_action}"'
            first_part = raw_action.split(' ')[0]
            action_name = re.sub(r'[^a-zA-Z0-9_]', '', first_part)

        for action in ACTION_REGISTRY:
            if action_name == action.name:
                return action(arguments)

        raise ValueError(f'Invalid action: {raw_action}\nExpected format: action_name(<arg1>, <arg2>, ...)')

    except Exception as e:
        logger.warning(f"Failed to parse '{raw_action}':\n{e}")

    return None


def extract_actions(answer: str, limit=5) -> list[Action]:
    from defame.tools import ACTION_REGISTRY

    actions_str = extract_last_code_block(answer).replace("markdown", "")
    if not actions_str:
        candidates = []
        for action in ACTION_REGISTRY:
            pattern = re.compile(rf'({re.escape(action.name)}\(.+?\))', re.DOTALL)
            candidates += pattern.findall(answer)
        actions_str = "\n".join(candidates)
    if not actions_str:
        # Potentially prompt LLM to correct format: Expected format: action_name("arguments")
        return []
    raw_actions = actions_str.split('\n')
    actions = []
    for raw_action in raw_actions:
        action = parse_single_action(raw_action)
        if action:
            actions.append(action)
        if len(actions) == limit:
            break
    return actions


def extract_verdict(response: str, classes: Collection[Label]) -> Optional[Label]:
    answer = extract_last_code_span(response)
    answer = re.sub(r'[^\w\-\s]', '', answer).strip().lower()

    if not answer:
        pattern = re.compile(r'\*\*(.*)\*\*', re.DOTALL)
        matches = pattern.findall(response) or ['']
        answer = matches[0]

    try:
        label = Label(answer)
        assert label in classes
        return label

    except ValueError:
        # TODO: Verify if this is necessary
        # Maybe the label is a substring of the response
        for c in classes:
            if c.value in response:
                return c

    return None


def extract_queries(response: str) -> list:
    from defame.tools import WebSearch
    matches = find_code_span(response)
    queries = []
    for match in matches:
        query = strip_string(match)
        action = WebSearch(f'"{query}"')
        queries.append(action)
    return queries


def extract_reasoning(answer: str) -> str:
    return remove_code_blocks(answer).strip()


## add function to extract labels and its confidence scores (added top-k verbalized confidence to judge.md file)
# def extract_confidence_scores(response: str, classes: Collection[Label]) -> Optional[dict[str, float]]:
#     # Add debugging statement
#     #logger.debug(f"DEBUG: Raw response for confidence extraction:\n{response}")

#     """ 
#     Extract confidence scores for each label from the response.
    
#     Expected LLM formats:
#     - "FALSE (70%) TRUE(30%)"
#     - "FALSE: 70%, TRUE: 30%"
#     - "70% FALSE, 30% TRUE"
#     - "FALSE(77.7%)TRUE(23.3%)"
#     - `true`: 95%
#     - `false`: 5%
    
    
#     Returns:
#         Dict mapping label names to confidence scores (0.0 to 1.0), or None if parsing fails
    
#     """
#     # Create empty dictionary to store confidence/probability scores
#     confidence_scores = {}

#     # Define multiple regex pattern to extract labels and confidence score from different LLM output formats

#     patterns = [
#         # Pattern 1: FALSE (70%), TRUE (30%)
#         r'(FALSE|TRUE)\s*\((\d+(?:\.\d+)?)%\)',
#         # Pattern 2: FALSE: 70%, TRUE: 30%
#         r'(FALSE|TRUE):\s*(\d+(?:\.\d+)?)%',
#         # Pattern 3: 70% FALSE, 30% TRUE
#         r'(\d+(?:\.\d+)?)%\s+(FALSE|TRUE)',
#         # Pattern 4: FALSE 70%, TRUE 30%
#         r'(FALSE|TRUE)\s+(\d+(?:\.\d+)?)%',
#         # Pattern 5: `true`: 95%, `false`: 5% (with backticks)
#         r'`(false|true)`:\s*(\d+(?:\.\d+)?)%',
#         # Pattern 6: true: 95%, false: 5% (without backticks)
#         r'(false|true):\s*(\d+(?:\.\d+)?)%',
#     ]

#     # Loop through all regex patterns to match output
#     for pattern in patterns:
#         matches = re.findall(pattern, response, re.IGNORECASE) #case insensitive
#         if matches:
#             for match in matches:
#                 if len(match) == 2:
#                     # Handle different match group orders
#                     if match[0].upper() in ['FALSE', 'TRUE']:
#                         label_str, confidence_str = match[0], match[1]
#                     else:
#                         confidence_str, label_str = match[0], match[1]

#                 label_upper = label_str.upper()
#                 # Convert percentage format to float with decimal (0-1 range)
#                 try:
#                     confidence_value = float(confidence_str) / 100.0
#                     confidence_scores[label_upper] = confidence_value
#                 except ValueError:
#                     continue

#             # If we found matches with this pattern, break
#             if confidence_scores:
#                 break
    
             
#     if not confidence_scores:
#         logger.warning(f"Could not extract confidence scores from response")
#         logger.debug(f"Response length: {len(response)} chars")
#         logger.debug(f"Response preview: {response[:200]}...")
#         return None
    
    
#     # Validate that only confidence scores for valid labels are provided
#     valid_labels = {label.value.upper() for label in classes}
#     for label in confidence_scores:
#         if label not in valid_labels:
#             logger.warning(f"Found confidence for invalid label: {label}")

#     # Validate that probabilites sum to 1 (specified in the judge.md prompt)
#     total_confidence = sum(confidence_scores.values())
#     if abs(total_confidence - 1.0) > 0:  
#         logger.warning(f"Confidence scores sum to {total_confidence:.1f}, not 1.0")
    
#     return confidence_scores if confidence_scores else None


# def extract_confidence_scores_json(response: str, classes: Collection[Label]) -> Optional[dict[str, float]]:
#     """
#     Extract confidence scores from JSON format in the response.
    
#     Expected format:
#     ```
#     CONFIDENCE_SCORES:
#     {
#       "false": 0.XX,
#       "true": 0.XX,
#       "not_enough_information": 0.XX
#     }
#     ```
    
#     Args:
#         response: LLM response text
#         classes: Collection of Label objects with .value attribute
        
#     Returns:
#         Dict mapping label names to confidence scores (0.0 to 1.0), or None if parsing fails
#     """
    
#     # Primary pattern: Look for CONFIDENCE_SCORES JSON block
#     json_pattern = r'CONFIDENCE_SCORES:\s*\{([^}]+)\}'
#     match = re.search(json_pattern, response, re.IGNORECASE | re.DOTALL)
    
#     if match:
#         try:
#             # Reconstruct the JSON
#             json_content = "{" + match.group(1) + "}"
#             parsed = json.loads(json_content)
            
#             # Normalize keys and validate
#             confidence_scores = {}
#             valid_labels = {label.value.upper() for label in classes}
            
#             for key, value in parsed.items():
#                 # Normalize key to match your label format
#                 normalized_key = key.strip().upper().replace(" ", "_")
#                 if normalized_key == "NOT_ENOUGH_INFORMATION":
#                     normalized_key = "NOT_ENOUGH_INFORMATION"
#                 elif normalized_key == "NOT ENOUGH INFORMATION":
#                     normalized_key = "NOT_ENOUGH_INFORMATION"
                
#                 # Validate value
#                 try:
#                     conf_value = float(value)
#                     if 0.0 <= conf_value <= 1.0:
#                         confidence_scores[normalized_key] = conf_value
#                     else:
#                         logger.warning(f"Invalid confidence value {conf_value} for {key}")
#                         return None
#                 except (ValueError, TypeError):
#                     logger.warning(f"Invalid confidence value {value} for {key}")
#                     return None
            
#             # Validate sum
#             total = sum(confidence_scores.values())
#             if abs(total - 1.0) > 0.02:  # Allow small rounding errors
#                 logger.warning(f"Confidence scores sum to {total:.3f}, not 1.0")
#                 # Normalize if close to 1.0
#                 if 0.95 <= total <= 1.05:
#                     confidence_scores = {k: v/total for k, v in confidence_scores.items()}
#                 else:
#                     return None
            
#             return confidence_scores
            
#         except json.JSONDecodeError as e:
#             logger.warning(f"JSON parsing failed: {e}")
    
#     # Fallback to your existing regex patterns
#     return extract_confidence_scores_fallback(response, classes)



# def extract_confidence_scores_json(response: str, classes: Collection[Label]) -> Optional[dict[str, float]]:
#     """
#     Extract confidence scores from JSON format in the response.
#     This version is robust to markdown code fences and other surrounding text.
#     """
#     # This pattern looks for "CONFIDENCE_SCORES:", then optionally skips over
#     # markdown fences like ```json, and then non-greedily captures everything
#     # from the first '{' to the final '}'
#     json_pattern = r'Confidence_machine_readable:\s*({.*?})'
#     match = re.search(json_pattern, response, re.IGNORECASE | re.DOTALL)
    
#     if match:
#         try:
#             # The pattern captures the full JSON string including braces
#             json_content = match.group(1)
#             json_content = re.sub(r'([a-zA-Z_]+):', r'"\1":', json_content) # Add quotes to unquoted keys
#             json_content = json_content.replace("'", '"') # Replace single quotes with double quotes
#             parsed = json.loads(json_content)
            
#             confidence_scores = {}
#             for key, value in parsed.items():
#                 # Normalize the key to be uppercase and use underscores
#                 normalized_key = key.strip().upper().replace(" ", "_")
                
#                 try:
#                     conf_value = float(value)
#                     if 0.0 <= conf_value <= 1.0:
#                         confidence_scores[normalized_key] = conf_value
#                     else:
#                         logger.warning(f"Invalid confidence value {conf_value} for {key}")
#                         # Don't return here, just skip the invalid value
#                 except (ValueError, TypeError):
#                     logger.warning(f"Could not convert confidence value '{value}' for key '{key}' to float.")
#                     continue
            
#             if not confidence_scores:
#                 logger.warning("JSON was found but contained no valid scores.")
#                 return None

#             # Validate sum
#             total = sum(confidence_scores.values())
#             if abs(total - 1.0) > 0.02:  # Allow small rounding errors
#                 logger.warning(f"Confidence scores sum to {total:.3f}, not 1.0. Normalizing...")
#                 if total > 0:
#                     confidence_scores = {k: v / total for k, v in confidence_scores.items()}
            
#             return confidence_scores
            
#         except json.JSONDecodeError as e:
#             logger.warning(f"Found a potential JSON block but parsing failed: {e}. Block: '{match.group(1)}'")
    
#     # If JSON parsing fails, log a warning and fall back to the regex method
#     logger.warning("Primary JSON extraction failed. Falling back to regex patterns.")
#     return extract_confidence_scores_fallback(response, classes)


# def extract_confidence_scores_fallback(response: str, classes: Collection[Label]) -> Optional[dict[str, float]]:
#     """
#     Fallback to existing regex patterns if JSON parsing fails
#     """
#     confidence_scores = {}
    
#     # Your existing patterns
#     patterns = [
#         r'(FALSE|TRUE|NOT_ENOUGH_INFORMATION|not enough information)\s*:\s*(\d+(?:\.\d+)?)%',
#         r'(FALSE|TRUE|NOT_ENOUGH_INFORMATION|not enough information)\s*\((\d+(?:\.\d+)?)%\)',
#         r'(\d+(?:\.\d+)?)%\s+(FALSE|TRUE|NOT_ENOUGH_INFORMATION|not enough information)',
#         r'`(false|true|not enough information)`:\s*(\d+(?:\.\d+)?)%',
#         r'[•\-\*]\s*(false|true|not enough information):\s*(\d+(?:\.\d+)?)%',
#     ]
    
#     for pattern in patterns:
#         matches = re.findall(pattern, response, re.IGNORECASE | re.MULTILINE)
        
#         for match in matches:
#             if len(match) == 2:
#                 if match[0].upper() in ['FALSE', 'TRUE', 'NOT_ENOUGH_INFORMATION'] or match[0].lower() == 'not enough information':
#                     label_str, confidence_str = match[0], match[1]
#                 else:
#                     confidence_str, label_str = match[0], match[1]
                
#                 # Normalize label
#                 label_upper = label_str.upper()
#                 if label_upper == 'NOT ENOUGH INFORMATION':
#                     label_upper = 'NOT_ENOUGH_INFORMATION'
                
#                 try:
#                     confidence_value = float(confidence_str) / 100.0
#                     confidence_scores[label_upper] = confidence_value
#                 except ValueError:
#                     continue
        
#         if len(confidence_scores) >= 2:
#             break
    
#     if not confidence_scores:
#         logger.warning("Could not extract confidence scores from response")
#         return None
    
#     # Validate
#     total_confidence = sum(confidence_scores.values())
#     if abs(total_confidence - 1.0) > 0.02:
#         logger.warning(f"Confidence scores sum to {total_confidence:.3f}, normalizing...")
#         if total_confidence > 0:
#             confidence_scores = {k: v/total_confidence for k, v in confidence_scores.items()}
    
#     return confidence_scores