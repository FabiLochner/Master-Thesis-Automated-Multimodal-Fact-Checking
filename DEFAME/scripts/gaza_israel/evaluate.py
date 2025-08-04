### This function imports the evaluate function to evaluate the gaza_israel dataset
## It uses the parameters that are set in the "default.yaml" file within the gaza_israel folder within the config folder 
## The base of this code is the evaluate.py files of the "mocheg" and "verite" folders within the "scripts" folder here


import warnings
from multiprocessing import set_start_method

from defame.eval.evaluate import evaluate

warnings.filterwarnings("ignore")

if __name__ == '__main__':  # evaluation uses multiprocessing
    set_start_method("spawn")
    evaluate(
        llm="gemini-2.0-flash-lite", #change to the LLM I use (see default.yaml file)
        tools_config=dict(
            searcher=dict(
                search_engine_config=dict(
                    google=dict(),
                    google_vision=dict(),
                ),
                limit_per_search=3
            ),
            geolocator=dict()
        ),
        fact_checker_kwargs=dict(
            procedure_variant="summary/dynamic", #use the dynamic DEFAME variant first
            interpret=False,
            decompose=False,
            decontextualize=False,
            filter_check_worthy=False,
            max_iterations=3,
            max_result_len=64_000,  # characters
        ),
        llm_kwargs=dict(temperature=0.01),
        benchmark_name="verite",
        benchmark_kwargs=dict(variant="dev"),
        allowed_actions=["web_search",
                         "image_search",
                         "reverse_search",
                         "geolocate"],
        n_samples=1,
        sample_ids=None, # list of integers
        random_sampling=False,
        print_log_level="info",
        n_workers=1,
        #continue_experiment_dir = "out/verite/verite/summary/dynamic/gpt_4o_mini/2025-03-21_20-42_default"
    )


