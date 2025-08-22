#### Write the class for the ukraine_russia dataset here now


## Import the same libraries that are also used for the other datasets/benchmarks


import os
from pathlib import Path
from typing import Iterator

import pandas as pd

from defame.common.medium import Image
from config.globals import data_root_dir
from defame.common import Label, Content
from defame.eval.benchmark import Benchmark
from defame.tools.text_extractor import OCR
from defame.tools.geolocator import Geolocate
from defame.tools.object_detector import DetectObjects
from defame.tools import WebSearch, ImageSearch, ReverseSearch





### create the class for the ukraine-russia dataset

class ukraine_russia(Benchmark):
    """ 
    Ukraine-Russia dataset with aggregated binary labels (True/False).

    The original 4 labels ("True", "False", "Misleading", "NEI") have been aggregated into 2 labels:

    - Original "True" -> "True"
    - Original "False", "Misleading", "NEI" -> "False"

    This creates a binary classification task.
    """    
    shorthand = "ukraine_russia"

    is_multimodal = True

    ## Update class mapping to binary classification task
    class_mapping = { #Use the spelling of the labels in my datasets for mapping here (Starts with capital letter)
        "True": Label.TRUE,
        "False": Label.FALSE, #The aggregated "False" label contains the original "False", "Misleading" and "NEI" sub-labels.

    }


    ## Test these first label definitions for now. Might need some adjustments.

    ## Update the class definitions to binary classification task and reflect the newly aggregated "False" label
    class_definitions = {
        Label.TRUE:
            "The claim is factually accurate when it is confirmed by evidence from multiple and reliable sources.",
        Label.FALSE:
            "The claim is not factually accurate. This is the case if one of the following three conditions is met:"
            "(1) The claim is demonstrably false when it is disproven by evidence from multiple and reliable sources,"
            "(2) The claim or image is taken out of context, i.e. the origin, content and/or meaning of a statement or an image is misrepresented. For example, an old claim or an old image is mispresented in a new context in a misleading way,"
            "(3) There is not enough evidence to verify the claim or the evidence is conflicting or self-contradictory.",
    
    }


    ## Could add extra prepare/plan/judge rules here (as in the other benchmarks). Leave this for later
    ### e.g., the extra rules used for the VERITE benchmark:

    # extra_prepare_rules = """**Assess Alignment**: Assess the alignment between image and text in complex scenarios. Prepare for varied real-world images and captions.
    # **Verify Context**: Examine the source and context of each image to understand its relationship with the accompanying text.
    # Start each claim with: The claim is that the image shows ... """

    # extra_plan_rules = """* **Consider Both Modalities Equally**: Avoid focusing too much on one modality at the expense of the other but always check whether the text claim is true or false.
    # * **Compare Image and Caption**: Verify the context of the image and caption.
    # * **Identify any potential asymmetry in the modalities**: Perform one image_search if the action is available to compare other images with the claim image."""

    # extra_judge_rules = """* **Caption Check First**: If the caption is factually wrong, then the claim is considered out-of-context.
    # * **Alignment Check of Image and Claim**: If the caption is factually correct, we need to check whether the image corresponds to the claim. 
    # Judge if there is any alignment issue between image and text. Does the image deliver any support for the claim or is it taken out of context?
    # If the claim text is actually true but the image shows a different event, then the verdict is out-of-context."""


    #Use the same 4 default tools as in the DEFAME paper. In case of testing additional tools, e.g., a manipulation detector for altered/AI-images, they need to be added here.
    available_actions = [WebSearch, Geolocate, ImageSearch, ReverseSearch]


    # Use the code from the benchmark.py file of the 'verite' folder as a base to load the dataset and adjust the code where it is necessary
    def __init__(self, variant="dev"): #TODO: adjust this to 'test' for the final evaluations 
        super().__init__(f"ukraine_russia ({variant})", variant)
        self.file_path = data_root_dir / "ukraine_russia/ukraine_russia_dataset_combined_010724_300425_final_binary.csv" #update the path for the dataset with aggregated binary labels
        if not self.file_path.exists():
            raise ValueError(f"Unable to locate ukraine_russia dataset at {data_root_dir.as_posix()}. "
                             f"See README.md for setup instructions.")
        self.data = self.load_data()
            

    
    def load_data(self) -> list[dict]:
        # Use the `dtype` parameter to force pandas to read 'Label_Binary' as a string.
        # This prevents pandas from automatically converting "True"/"False" strings into booleans,
        # which would cause a KeyError in the self.class_mapping lookup later.
        df = pd.read_csv(self.file_path, dtype = {"Label_Binary": str})
        data = []
        for i, row in df.iterrows():
            # Handle multimodal claims: Check that the row has an image (should not be NaN or empty)
            if pd.notna(row['Image_Path']) and row['Image_Path']:
                image_path = data_root_dir / f"ukraine_russia/{row['Image_Path']}"
                # Check that the image actually exists on the disk
                if not os.path.exists(image_path):
                    print(f"Warning: Missing image file for row {i}: {image_path}")
                    continue
                image = Image(image_path)
                claim_text = f"{image.reference} {row['Claim']}" # reformulated, final claims are stored in this column

            # Handle text-only claims
            else:
                image = None
                claim_text = row['Claim']

            assert isinstance(i, int)

            # Extract claim types from dataset. The CSV is expected to store the columns as boolean values.
            text_only_flag = row.get("Text_Only_Claim", False) == True
            normal_image_flag = row.get("Normal_Image", False) == True
            ai_image_flag = row.get("AI_Generated_Image", False) == True
            altered_image_flag = row.get("Altered_Image", False) == True

            entry = {
                "id": i,
                "content": Content(content=claim_text, id_number=i),
                "label": self.class_mapping[row["Label_Binary"]], # adjust it to the aggregated binary label column
                "justification": row.get("Context/Label_Explanation", ""), # the label explanations/justifications of the fact-checking websites is stored in this column

                # Add claim type keys for evaluation 
                "claim_text_only": text_only_flag,
                "claim_normal_image": normal_image_flag,
                "claim_ai_image": ai_image_flag,
                "claim_altered_image": altered_image_flag,
            }
            data.append(entry)

        return data 
    

    def __iter__(self) -> Iterator[dict]:
        return iter(self.data)
