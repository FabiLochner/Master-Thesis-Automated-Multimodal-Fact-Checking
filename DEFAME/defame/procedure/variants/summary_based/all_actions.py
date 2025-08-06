from typing import Any

from defame.common import Report, Label, logger
from defame.procedure.variants.summary_based.dynamic import DynamicSummary
from defame.tools.search.common import WebSearch, ImageSearch


class AllActionsSummary(DynamicSummary):
    def apply_to(self, doc: Report) -> (Label, dict[str, Any]):
        n_iterations = 0
        label = Label.NEI
        while label == Label.NEI and n_iterations < self.max_iterations:
            logger.log("Not enough information yet. Continuing fact-check...")
            n_iterations += 1
            actions, reasoning = self.planner.plan_next_actions(doc, all_actions=True)

            """ 
            Adjust the text claim handling to my datasets: both contain text-only claims and claims with images.
            The default DEFAME implementation assumed that all claims have images: 
            
            text = f'"{doc.claim.text.split(">", 1)[1].strip()}"'
            
            Thus, it raised errors for the text-only claims in my datasets.
            
            """

            ## Handle both text-only claims and claims with images

            if ">" in doc.claim.text: ## Claims with images
                text = f'"{doc.claim.text.split(">", 1)[1].strip()}"'  ## Remove the '<image: >' from claim for Web/Image Search
            else: ## Text-only claims
                text = f'"{doc.claim.text.strip()}"' ## Only remove whitespaces
            
            actions.append(WebSearch(text))
            actions.append(ImageSearch(text))
            if len(reasoning) > 32:  # Only keep substantial reasoning
                doc.add_reasoning(reasoning)
            doc.add_actions(actions)
            if actions:
                evidences = self.actor.perform(actions, doc)
                doc.add_evidence(evidences)  # even if no evidence, add empty evidence block for the record
                self._develop(doc)
            label = self.judge.judge(doc, is_final=n_iterations == self.max_iterations or not actions)
        return label, {}
