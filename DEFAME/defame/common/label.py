from enum import Enum


class Label(Enum):
    SUPPORTED = "supported"
   # NEI = "not enough information"  ## commenting the original NEI out to avoid conflicting issues with my NEI definition
    REFUTED = "refuted"
    CONFLICTING = "conflicting evidence"
    CHERRY_PICKING = "cherry-picking"
    REFUSED_TO_ANSWER = "error: refused to answer"
    OUT_OF_CONTEXT = "out of context"
    MISCAPTIONED = "miscaptioned"

    ## Adding the labels used in my datasets
    TRUE = "true"
    FALSE = "false"
    MISLEADING = "misleading"
    NEI = "not enough information"



DEFAULT_LABEL_DEFINITIONS = {
    Label.SUPPORTED: "The knowledge from the fact-check supports or at least strongly implies the Claim. "
                     "Mere plausibility is not enough for this decision.",

    ### Commenting the original NEI definition of the DEFAME authors out to avoid conflicting
    ## issues with my NEI definition - shown below at the end. 

   # Label.NEI: "The fact-check does not contain sufficient information to come to a conclusion. For example, "
    #           "there is substantial lack of evidence. In this case, state which information exactly "
     #          "is missing. In particular, if no RESULTS or sources are available, pick this decision.",
    Label.REFUTED: "The knowledge from the fact-check clearly refutes the Claim. The mere absence or lack of "
                   "supporting evidence is not enough reason for being refuted (argument from ignorance).",
    Label.CONFLICTING: "The knowledge from the fact-check contains conflicting evidence from multiple "
                       "RELIABLE sources. Even trying to resolve the conflicting sources through additional "
                       "investigation was not successful.",
    Label.OUT_OF_CONTEXT: "The image is used out of context. This means that while the caption may be factually"
                          "correct, the image does not relate to the caption or is used in a misleading way to "
                          "convey a false narrative.",
    Label.MISCAPTIONED: "The claim has a true image, but the caption does not accurately describe the image, "
                        "providing incorrect information.",



    ### Adding the label definitions used in the label aggregation step within my dataset creation pipeline.

    Label.TRUE: "The knowledge from the fact-check supports the Claim. The Claim is factually accurate when it is confirmed by "
                "evidence from multiple and reliable sources. Mere plausibility is not enough for this decision.",

    Label.FALSE: "The knowledge from the fact-check clearly refutes the Claim. The Claim is demonstrably false when it is"
                 "disproven by evidence from multiple and reliable sources. The mere absence or lack of "
                   "supporting evidence is not enough reason for being refuted.",

    Label.MISLEADING: "The claim or image is taken out of context, mispresented in a wrong context or necessary context is omitted."
                      "For example, an old claim or image is misrepresented in a new and different context. Other examples are"
                      "to omit the context of a claim or image or to misinterpret and distort the meaning of a claim. "
                      "In contrast to the label 'FALSE' the claim or image can also contain some true elements, which are taken out of context.",    ## VERITE -> all claims had images and thus the out-of-context and miscaptioned labels are related to images
                            ## in my datasets misleading claims are both text-only claims and claims with images

    Label.NEI: "The fact-check does not contain sufficient information to come to an conclusion. For example,"
                "there is substantial lack of evidence or the evidence is inconclusive, conflicting or self-contradictory. "
                "In the case of a lack of evidence, state which information exactly is missing. In particular, if no RESULTS or sources are available, pick this decision."

}







""" Labeling definitions (True) of fact-checking websites:


- "We state an item is true when multiple and reliable sources have confirmed the information to be authentic." (AFP Factcheck)
- "Content or statements that are accurate." (Reuters)
- "This rating indicates that the primary elements of a claim are demonstrably true." (Snopes)
- "The statement is accurate and there’s nothing significant missing." (Politifact)
- "The primary aspects of the claim are true and can be backed up with evidence to prove it." (misbar.com)
- "This claim is entirely justified by the available evidence and helpful in understanding the point at issue." (logicallyfacts.com)
- "The claim is accurate with supporting evidence." (newsmeter.in)
- "Claim is provably accurate, with no key context omitted." (usatoday.com)
- "The primary aspects of the claim are true and can be backed up with evidence." (checkyourfact.com)
- "The claim is accurate with supporting evidence." (newschecker.in)
- "The claim is verifiably correct. Primary source evidence proves the claim to be true." (newsweek.com)



What are the common elements among all of the definitions above?

- (primary) aspects of the claim are factually accurate and are supported/proven by evidence from multiple and reliable sources


"""





""" Labeling definitions (False) of fact-checking websites:


- "We state an item is false when multiple and reliable sources disprove it." (AFP Factcheck)
- "We rate a claim or media content as false when it can be independently disproven, such as imposter content and hoaxes. Statements are also rated false when several credible sources and experts disprove the claim." (Reuters)
- "This rating indicates that the primary elements of a claim are demonstrably false." (Snopes)
- "The statement is not accurate." (Politifact)
- "The primary aspects of the claim are false and lack supporting evidence. Elements of a claim are demonstrably false." (misbar.com)
- "This claim is entirely unjustified by the available evidence." (logicallyfacts.com)
- The claim is inaccurate and misleading." (newsmeter.in)
- "Claim is provably wrong." (usatoday.com)
- "The primary aspects of the claim are false and lack supporting evidence." (checkyourfact.com)
- "The claim is inaccurate and misleading." (newschecker.in)
- "The claim is demonstrably false. Primary source evidence proves the claim to be false." (newsweek.com)
- "This applies to content where claim(s) are factually inaccurate. This includes claims by top government officials and newsmakers which may not be eligible for rating in Facebook’s Claim check. Rappler reserves the right to flag such content as false as a way to warn our audience." (rappler.com)



What are the common elements among all of the definitions above?
- claim is demonstrably false/inaccurate
- disproven by evidence from multiple and reliable sources


"""




""" Labeling definitions (Misleading) of fact-checking websites:

- "We state an item is misleading when it uses genuine information (text, photo or video), taken out of context or mixed with false context." (AFP Factcheck)
- "Genuine content that includes factual inaccuracies or missing context with suspected intent to deceive or harm." (Reuters)
- "This rating is used with photographs and videos that are “real” (i.e., not the product, partially or wholly, of digital manipulation) but are nonetheless misleading because they are accompanied by explanatory material that falsely describes their origin, context, and/or meaning." (Snopes)
- "The claim has significant elements of both truth and falsity to it such that it could not fairly be described by any other rating. The claim contains misleading information, bias, stereotype, hate speech, irrelated data, inaccurate translation, or context fragmentation." (misbar.com)
-  "This claim is mostly unhelpful in understanding the point at issue, even though elements of this claim may be justified by available evidence." (logicallyfacts.com)
-  "The claim has elements of truth but is taken out of context or misrepresented." (newsmeter.in)
- "Claim is largely accurate but misleads by omitting key context." (usatoday.com)
- "The claim contains some true information but also contains factual inaccuracies that make it misleading." (checkyourfact.com)
- "The claim has elements of truth but is taken out of context or misrepresented." (newschecker.in)
- "The claim is based on media that has been altered from its original form—such as an edited video or image—and is now misleading, misrepresentative, or deceptive, either intentionally or unintentionally." (newsweek.com)
- "The content may mislead without additional context." (rappler.com)


What are the common/core elements among all of the definitions above?
- claim misleads because it is taken out-of-context, misrepresented in a wrong context/mixed with false context or necessary context is left out
- containing some elements of truth or true and false elements -> also include this in definition or not? -> no



examples from my datasets: 
- old/outdated images or text-claims are misrepresented in new contexts
- the context of a statement/claim is left out and would be necessary to understand it. Thus it misleads the audience
- misinterpretation of a claim by social media users


#### Misleading -> Making the difference to "False" and "NEI" clear


"""



""" Labeling definitions (NEI) of fact-checking websites:

- "When a claim has no credible evidence and cannot be independently verified." (Reuters)
- "This rating applies to a claim for which we have examined the available evidence but could not arrive at a true or false determination, meaning the evidence is inconclusive or self-contradictory." (Snopes)
- "This claim cannot be verified based on the available evidence." (logicallyfacts.com)
- "There’s not enough evidence to establish a claim as true or false. The claim may have been made prematurely, or there might be conflicting data." (checkyourfact.com)
- "The claim could be true or false, but there is at the time of publication insufficient publicly-available evidence to prove so either way. The claim should be treated with caution and skepticism until more evidence becomes available to make a conclusive determination." (newsweek.com)



What are the common/core elements among all of the definitions above?

- claim cannot be verified due to a lack of, inconclusive, conflicting or self-contradictory evidence


"""
