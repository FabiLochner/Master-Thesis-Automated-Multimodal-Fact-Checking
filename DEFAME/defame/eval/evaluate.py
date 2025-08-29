import csv
import inspect
import json
import re
import time
import traceback
from multiprocessing import Process, Queue
from pathlib import Path
from queue import Empty
from typing import Sequence, Optional

import nltk
import numpy as np
import pandas as pd
import torch
import yaml
# from rouge_score import rouge_scorer
# from datasets import load_metric
from nltk.tokenize.treebank import TreebankWordDetokenizer
from sklearn.metrics import precision_score, recall_score, f1_score, matthews_corrcoef, accuracy_score, balanced_accuracy_score, fbeta_score, confusion_matrix # added metrics for evaluating my dataset: MCC, Balanced Accuracy, F-beta score (F0.5-score), Confusion Matrix to compute True Negative Rate/Specificity
from tqdm import tqdm

from defame.common import Label, logger, Report
from defame.common.modeling import model_specifier_to_shorthand, AVAILABLE_MODELS, make_model
from defame.eval import load_benchmark
from defame.eval.averitec.benchmark import AVeriTeC
from defame.eval.averitec.compute_score import compute_averitec_score
from defame.eval.benchmark import Benchmark
from defame.eval.mocheg.benchmark import MOCHEG
from defame.eval.gaza_israel.benchmark import gaza_israel #import class gaza_israel benchmark
from defame.eval.ukraine_russia.benchmark import ukraine_russia #import class ukraine_russia benchmark
from defame.fact_checker import FactChecker
from defame.tools import initialize_tools, Searcher
from defame.tools.search.knowledge_base import KnowledgeBase
from defame.utils.console import green, red, bold, sec2hhmmss, sec2mmss, num2text
from defame.utils.plot import plot_confusion_matrix
from defame.utils.utils import unroll_dict


def evaluate(
        llm: str,
        benchmark_name: str,
        tools_config: dict[str, dict],
        experiment_name: str = None,
        fact_checker_kwargs: dict = None,
        llm_kwargs: dict = None,
        benchmark_kwargs: dict = None,
        allowed_actions: list[str] = None,
        n_samples: int = None,
        sample_ids: list[int] = None,
        random_sampling: bool = False,
        print_log_level: str = "info",
        continue_experiment_dir: str = None,
        n_workers: int = None,
):
    assert not n_samples or not sample_ids

    is_resumed = continue_experiment_dir is not None

    status_verb = "Resuming" if is_resumed else "Starting"
    exp_name_str = f" '{bold(experiment_name)}'" if experiment_name else ""
    print(f"{status_verb} evaluation{exp_name_str} on {benchmark_name}.")

    if llm_kwargs is None:
        llm_kwargs = dict()

    benchmark = load_benchmark(benchmark_name, **benchmark_kwargs)
    is_test = benchmark.variant == "test"

    llm = model_specifier_to_shorthand(llm) if llm not in AVAILABLE_MODELS["Shorthand"].values else llm
    if fact_checker_kwargs is None or "procedure_variant" not in fact_checker_kwargs:
        procedure_variant = FactChecker.default_procedure
    else:
        procedure_variant = fact_checker_kwargs["procedure_variant"]

    logger.set_experiment_dir(path=continue_experiment_dir,
                              benchmark_name=benchmark.shorthand,
                              procedure_name=procedure_variant,
                              model_name=llm,
                              experiment_name=experiment_name)
    logger.set_log_level(print_log_level)

    n_devices = torch.cuda.device_count()
    if n_workers is None:
        match llm:
            case "llama3_8b":
                n_workers = 8
            case "llama3_70b":
                n_workers = 3  # only 3 copies fit on 8 A100 GPUs
            case _:
                n_workers = n_devices * 2  # 2 workers per GPU

    # Save hyperparams based on the signature of evaluate()
    if not is_resumed:
        signature = inspect.signature(evaluate)
        logger.save_config(signature, locals(), benchmark)

    # Load the tools for sanity check
    tools = initialize_tools(tools_config, llm=None)

    if allowed_actions is None:
        allowed_actions = benchmark.available_actions
    else:
        allowed_actions = [a for a in benchmark.available_actions if a.name in allowed_actions]

    # Verify that each tool is relevant (i.e. offers at least one allowed action)
    for tool in tools:
        for action in tool.actions:
            if action in allowed_actions:
                break
        else:
            logger.info(f"Tool {tool.name} offers only forbidden actions. You may exclude this tool.")

    # Verify that each allowed action has a corresponding tool
    for action in allowed_actions:
        for tool in tools:
            if action in tool.actions:
                break
        else:
            logger.warning(f"No Tool available for action {action.name}.")

    # TODO: Print a nice, colored list of tools and their usage

    del tools

    if random_sampling:
        benchmark.shuffle()  # TODO: Add seed

    if n_samples:
        samples = benchmark[:n_samples]
    elif sample_ids:
        samples = [benchmark.get_by_id(i) for i in sample_ids]
    else:
        samples = benchmark

    # Exclude already existing samples (relevant if evaluation is resumed)
    if is_resumed:
        samples_to_evaluate = []
        # Retrieve the IDs of already checked claims
        predictions_path = continue_experiment_dir + "/predictions.csv"
        df = pd.read_csv(predictions_path)
        checked_claim_ids = df["sample_index"].to_numpy()

        # Only keep samples that haven't been checked yet
        for sample in samples:
            # sample["id"] should be convertable into a number type for indexing
            if int(sample["id"]) not in checked_claim_ids:
                samples_to_evaluate.append(sample)
    else:
        samples_to_evaluate = samples

    # Update number of to-be-checked samples
    n_samples = len(samples_to_evaluate)

    if n_samples == 0:
        raise RuntimeError("Nothing to evaluate.")

    n_workers = min(n_workers, n_samples)

    is_averitec = isinstance(benchmark, AVeriTeC)

    start_time = time.time()

    input_queue = Queue()
    output_queue = Queue()
    devices_queue = Queue()
    error_queue = Queue()

    fact_checker_kwargs.update(dict(
        available_actions=allowed_actions,
        class_definitions=benchmark.class_definitions,
        extra_prepare_rules=benchmark.extra_prepare_rules,
        extra_plan_rules=benchmark.extra_plan_rules,
        extra_judge_rules=benchmark.extra_judge_rules,
    ))

    print(f"Evaluating {n_samples} samples using {n_workers} workers...")

    for d in range(n_workers):
        devices_queue.put(d % n_devices if n_devices > 0 else None)

    # Fill the input queue with benchmark instances
    for instance in samples_to_evaluate:
        content = instance["content"]
        input_queue.put(content)

    # Optionally, add sentinel values to indicate shutdown after all tasks are done
    for _ in range(n_workers):
        input_queue.put(None)

    # Initialize and start worker processes
    workers = []
    for i in range(n_workers):
        p = Process(
            target=fact_check,
            args=(
                llm,
                llm_kwargs,
                fact_checker_kwargs,
                tools_config,
                print_log_level,
                logger.target_dir,
                is_averitec,
                input_queue,
                output_queue,
                devices_queue,
                error_queue,
                i  # worker_id
            )
        )
        p.start()
        workers.append(p)
        logger.info(f"Started Worker {i} with PID {p.pid}.")

    process = tqdm(range(n_samples), smoothing=0.02)
    n_completed = 0

    try:
        while n_completed < n_samples:
            try:
                doc, meta = output_queue.get(timeout=60)
                process_output(doc, meta, benchmark, is_test)
                n_completed += 1
                process.update(1)

            except Empty as e:
                # Check the status of each worker
                for i, worker in enumerate(workers):
                    if not worker.is_alive() and worker.exitcode != 0:
                        logger.error(f"Worker {i} has died unexpectedly. Exit code: {worker.exitcode}")

                # Log any potential error reported by workers
                while not error_queue.empty():
                    error_message = error_queue.get()
                    logger.error(error_message)

                # Quit if all workers are dead
                if np.all([not worker.is_alive() for worker in workers]):
                    break

    except Exception as e:
        logger.error(f"An unexpected error occurred in the main process:") #changed to error to avoid crashing (for debugging purposes)
        logger.error(traceback.format_exc())

    finally:
        for i, worker in enumerate(workers):
            if worker.is_alive():
                worker.terminate()
                worker.join()
                logger.info(f"Worker {i} has been terminated gracefully.")
        logger.info("All workers are terminated.")

    end_time = time.time()
    duration = end_time - start_time

    stats = {
        "Number of workers": n_workers,
        "Total run duration": duration,
    }

    finalize_evaluation(stats, logger.target_dir, benchmark)


def process_output(doc: Report, meta: dict, benchmark: Benchmark, is_test: bool):
    content = doc.claim.original_context
    claim_id = content.id_number
    instance = benchmark.get_by_id(claim_id)
    prediction = doc.verdict
    #confidence_scores = doc.confidence or {} # add confidence scores. use empty dictionary if confidence is None (to avoid crashes)

    # Special output processing for AVeriTeC
    if isinstance(benchmark, AVeriTeC):
        if prediction == Label.CHERRY_PICKING:
            # Merge cherry-picking and conflicting label
            prediction = Label.CONFLICTING

        pred_label = benchmark.get_class_name(prediction)
        averitec_out_instance = {
            "claim_id": claim_id,
            "claim": content.text,
            "pred_label": pred_label
        }

        if "q_and_a" in meta:
            averitec_out_instance["evidence"] = meta["q_and_a"]

        logger.save_next_averitec_out(averitec_out_instance)

    logger.save_next_prediction(
        sample_index=claim_id,
        claim=doc.claim.text,
        target=instance.get("label"),
        justification=doc.justification,
        predicted=prediction,
        gt_justification=instance.get("justification"),
       # confidence_TRUE = confidence_scores.get("TRUE") if confidence_scores else np.nan, # add confidence score for TRUE label
        #confidence_FALSE = confidence_scores.get("FALSE") if confidence_scores else np.nan # add confidence score for FALSE label
    )
    logger.save_next_instance_stats(meta["Statistics"], instance['id'])

    if not is_test:
        prediction_is_correct = instance["label"] == prediction
        if prediction_is_correct:
            logger.log(bold(green("CORRECT\n")))
        else:
            logger.log(bold(red("WRONG - Ground truth: " + instance["label"].value + "\n")))


def aggregate_stats(instance_stats: pd.DataFrame, category: str) -> dict[str, float]:
    """Sums the values for all instances for all the columns the name of
    which begin with 'category'."""
    aggregated_stats = dict()
    columns = list(instance_stats.columns)
    for column in columns:
        if column.startswith(category):
            aggregated = instance_stats[column].sum()
            if isinstance(aggregated, np.integer):
                aggregated = int(aggregated)
            elif isinstance(aggregated, np.floating):
                aggregated = float(aggregated)
            aggregated_stats[column] = aggregated
    return unroll_dict(aggregated_stats)


def finalize_evaluation(stats: dict,
                        experiment_dir: str | Path,
                        benchmark: Benchmark):
    """Takes a dictionary of experiment statistics, computes experiment metrics, and saves
    all the values in a YAML file. Also plots a confusion matrix if ground truth is available."""
    experiment_dir = Path(experiment_dir)
    is_averitec = isinstance(benchmark, AVeriTeC)
    is_mocheg = isinstance(benchmark, MOCHEG)
    # Add my two datasets here
    is_gaza_israel = isinstance(benchmark, gaza_israel)
    is_ukraine_russia = isinstance(benchmark, ukraine_russia)
    is_test = benchmark.variant == "test"
    try:
        instance_stats = pd.read_csv(experiment_dir / logger.instance_stats_filename)
    except Exception:
        print("Terminated before instance_stats.csv was created. ")
        return

    # Add aggregated statistics from individual claims
    stats.update({"Time per claim": instance_stats["Duration"].mean()})
    stats.update(aggregate_stats(instance_stats, category="Model"))
    stats.update(aggregate_stats(instance_stats, category="Tools"))

    # Retrieve predictions and ground truth
    df = pd.read_csv(experiment_dir / logger.predictions_filename)

    ## Added code: Change the column order of the predictions.csv file 
    ## 1) Set desired column order
    desired_column_order = [
        'sample_index',
        'claim',
        'predicted',
       # 'confidence_TRUE',
        #'confidence_FALSE',
        'target',
        'correct',
        'justification',
        'gt_justification'
    ]

    ## 2) Create a final list of columns that actually exist in the df (error prevention)
    final_column_order = [col for col in desired_column_order if col in df.columns]

    ## 3) Reorder the df using the final list
    df = df[final_column_order]

    # Sort by 'sample_index' column
    df = df.sort_values(by="sample_index").reset_index(drop=True)
    df.to_csv(experiment_dir / logger.predictions_filename, index=False)

    predicted_labels = df["predicted"].to_numpy()
    if is_averitec:
        ground_truth_labels = None if is_test else df["target"].to_numpy()
    else:
        # Assuming that the test set also has target labels.
        ground_truth_labels = df["target"].to_numpy()

    predicted_justifications = df["justification"].apply(remove_urls_and_brackets)
    ground_truth_justifications = df["gt_justification"].apply(remove_urls_and_brackets)

    # Compute the metrics based on the given benchmark. 
    ## 1) For my two dataset, a two-level evaluation approach is used (dataset-level and claim-type level)
    ## 2) For other datasets, the original code with the def compute_metrics is used

    if is_gaza_israel or is_ukraine_russia:
        # Compute dataset-level metrics
        metrics_dataset_stats = compute_metrics_dataset_level(predicted_labels, ground_truth_labels)
        # Compute claim-type-level metrics
        metrics_claim_types_stats = compute_metrics_claim_type_level(benchmark, predicted_labels, ground_truth_labels)
        # Combine the stats into a single dictionary
        stats["Predictions"] = {
            "Dataset_Metrics": metrics_dataset_stats,
            "Claim_Type_Metrics": metrics_claim_types_stats
        }

    else:
        # Use original def compute_metrics for other benchmarks/datasets
        metric_stats = compute_metrics(predicted_labels,
                                   ground_truth_labels,
                                   predicted_justifications=predicted_justifications,
                                   ground_truth_justifications=ground_truth_justifications,
                                   is_mocheg=is_mocheg)
        stats["Predictions"] = metric_stats


    save_stats(stats, target_dir=experiment_dir)

    logger.info(f"All outputs saved in {experiment_dir.as_posix()}.")

    if not is_test:

        # Making the plotting of the confusion matrix more robust to handle possible capitalization issues between label values in loaded datasets (gaza-israel, ukraine-russia)
        # and the class mapping and definitions in the respective benchmark.py files for both datasets (gaza-israel, ukraine-russia), see: Practical /defame/eval/gaza_israel/benchmark.py and /defame/eval/ukraine_russia/benchmark.py 

        # Step 1: Define the canonical source of truth for the labels.
        # This gets the Enum objects, e.g., [<Label.TRUE: 'TRUE'>, <Label.FALSE: 'FALSE'>]
        canonical_enums = benchmark.get_classes()
        # Convert them to a list of uppercase strings, e.g., ['TRUE', 'FALSE']
        # This list will have a consistent order every time.
        #canonical_labels_upper = [label.name for label in canonical_enums] 

        # Step 2: Normalize the raw data from the CSV to match the canonical format.
        # This converts the arrays to string type (to be safe) and then to uppercase.
        # It handles any capitalization in the CSV ('True', 'true', 'TRUE' all become 'TRUE').
        predicted_labels_upper = np.char.upper(predicted_labels.astype(str))
        ground_truth_labels_upper = np.char.upper(ground_truth_labels.astype(str))

        
        # if is_averitec:
        #    benchmark_classes.remove(Label.CHERRY_PICKING)

        plot_confusion_matrix(predicted_labels_upper, #adjusted to the upper-cased predicted labels
                              ground_truth_labels_upper, #adjusted to the upper-cased ground truth labels
                              canonical_enums, # use the benchmark enum objects 
                              benchmark_name=benchmark.name,
                              save_dir=experiment_dir)

        if is_averitec:
            averitec_out_path = experiment_dir / logger.averitec_out_filename
            scores = compute_averitec_score(benchmark.file_path, averitec_out_path)
            scores_path = experiment_dir / "averitec_scores.yaml"
            with open(scores_path, "w") as f:
                yaml.dump(scores, f, sort_keys=False)






## Add function to compute True Negative Rate (TNR)/Specificty 
def compute_tnr(y_true, y_pred):

    """
    This function computes the True Negative Rate (TNR)/Specificity using the confusion matrix.
    TNR = TN / (TN + FP)

    The function is written for binary classifications only.
    
    """             

    labels = np.unique(np.append(y_true, y_pred))
    cm = confusion_matrix(y_true, y_pred, labels=labels)
    tn = cm[0,0]
    # Handle the case of no available false positives
    try:
        fp = cm[0,1]
    except IndexError:
        fp = 0 # no false positives available in confusion matrix
    denom = tn + fp
    return float(tn / denom) if denom > 0 else np.nan
    

# Add function to compute metrics on claim type level for my datasets
def compute_metrics_claim_type_level(benchmark: Benchmark, predicted_labels: np.ndarray, ground_truth_labels: Optional[np.ndarray] = None):
    

    is_gaza_israel = isinstance(benchmark, gaza_israel)
    is_ukraine_russia = isinstance(benchmark, ukraine_russia)

    # Ukraine-russia dataset has only 3 claim types. Gaza-israel dataset has all 4 claim types

    if is_ukraine_russia:
        claim_types = [
            ("Claims_Text_Only", "claim_text_only"),
            ("Claims_Normal_Images", "claim_normal_image"), 
            ("Claims_Altered_Images", "claim_altered_image")
        ]

    elif is_gaza_israel:
        claim_types = [
            ("Claims_Text_Only", "claim_text_only"),
            ("Claims_Normal_Images", "claim_normal_image"),
            ("Claims_AI_Images", "claim_ai_image"),
            ("Claims_Altered_Images", "claim_altered_image")
        ]

    else:
        # For other benchmarks, return empty metrics (not implemented)
        print(f"Warning: Claim type metrics not implemented for benchmark type: {type(benchmark).__name__}")
        return {"Claim_Type_Metrics": {}}

    # Initialize metrics dictionary with only the relevant claim types
    metrics_claim_types = {}
    for claim_type, _ in claim_types:
        metrics_claim_types[claim_type] = {}


    # 1) Get all instances of each benchmark
    #all_instances = benchmark.data
    # claims_text_only_mask = [instance.get("claim_text_only", False) for instance in all_instances]
    # claims_normal_image_mask = [instance.get("claim_normal_image", False) for instance in all_instances]
    # claims_ai_image_mask = [instance.get("claim_ai_image", False) for instance in all_instances]
    # claims_altered_image_mask = [instance.get("claim_altered_image", False) for instance in all_instances]

    # 2) Compute metrics for the different claim types
        # For text-only claims and normal images: 
            # Both datasets have both ground truth labels ("True", "False"). Hence, more metrics can be computed.
        # For claims with ai & altered images:
            # Both datasets have only 1 ground truth label ("False"). Hence, less metrics can be computed.

    # Make the function robust when a sample of a dataset is used for evaluation. We should not get IndexErrors.
    # Get the evaluated instances instead of all instances (as used before). We can get this information from the predictions file
    try:
        # Read the predictions to get which samples were evaluated
        df = pd.read_csv(Path(logger.target_dir) / logger.predictions_filename)
        evaluated_sample_indices = df["sample_index"].to_numpy()
        # Get only the instances that wer evaluated
        evaluated_instances = [benchmark.get_by_id(idx) for idx in evaluated_sample_indices]

    except Exception as e:
        print(f"Warning: Could not read predictions file to determine evaluated instances: {str(e)}")

    # Process each claim type
    for claim_type, claim_key in claim_types:
        # Create mask for this claim type using evaluated instances only
        mask = [instance.get(claim_key, False) for instance in evaluated_instances]

        if not any(mask):
            print(f"Warning: No claims found for claim type: {claim_type}") 
            continue

        # Filter labels and predictions for each claim type
        gt_subset = ground_truth_labels[mask] if ground_truth_labels is not None else None
        pred_subset = predicted_labels[mask]

        n_samples_subset = len(pred_subset)
        n_refused_subset = np.count_nonzero(np.array(pred_subset) == "REFUSED_TO_ANSWER")

        try:
            ## Text-Only Claims and Normal_Images
            if claim_type in ["Claims_Text_Only", "Claims_Normal_Images"]:
                labels_subset = np.unique(np.append(gt_subset, pred_subset))

                # 1) Overall metrics per claim type
                acc = accuracy_score(gt_subset, pred_subset) # added accuracy not as performance metrics, but might be relevant for uncertainty estimation evaluation (is used in expected calibration error)
                balanced_acc = balanced_accuracy_score(gt_subset, pred_subset)
                mcc = matthews_corrcoef(gt_subset, pred_subset)
                tnr = compute_tnr(gt_subset, pred_subset)

                # 2) Metrics per label
                precision = precision_score(gt_subset, pred_subset, labels = labels_subset, average = None, zero_division=0)
                recall = recall_score(gt_subset, pred_subset, labels=labels_subset, average=None, zero_division=0)
                f1_scores = f1_score(gt_subset, pred_subset, labels=labels_subset, average=None, zero_division=0)
                f05_scores = fbeta_score(gt_subset, pred_subset, beta = 0.5, labels=labels_subset, average=None, zero_division=0)

                # 3) Absolute number of correct and wrong predictions
                correct_predictions = np.asarray(np.array(pred_subset) == np.array(gt_subset))
                n_correct = np.sum(correct_predictions)
                n_wrong = n_samples_subset - n_correct - n_refused_subset


                metrics_claim_types[claim_type].update({
                    "Accuracy": float(round(acc, 2)),
                    "Balanced_Accuracy": float(round(balanced_acc, 2)),
                    "Matthews_Correlation_Coefficient": float(round(mcc, 2)),
                    "True_Negative_Rate/Specificity": "N/A" if np.isnan(tnr) else float(round(tnr, 2))
                })

                for label, p, r, f1, f05 in zip(labels_subset, precision, recall, f1_scores, f05_scores):
                    metrics_claim_types[claim_type].update({
                        f"{label}_Precision": float(round(p, 2)),
                        f"{label}_Recall": float(round(r, 2)),
                        f"{label}_F1_Score": float(round(f1, 2)),
                        f"{label}_F0.5_Score": float(round(f05, 2))
                    })

                metrics_claim_types[claim_type].update({
                    "Correct_Predictions": int(n_correct),
                    "Wrong_Predictions": int(n_wrong),
                })

            ## AI-Images & Altered Images
            else:
                # 1) Overall metrics per claim type
                acc = accuracy_score(gt_subset, pred_subset) # added accuracy not as performance metrics, but might be relevant for uncertainty estimation evaluation (is used in expected calibration error)
                balanced_acc = balanced_accuracy_score(gt_subset, pred_subset)
                tnr = compute_tnr(gt_subset, pred_subset)

                # 2) Absolute number of correct and wrong predictions
                correct_predictions = np.asarray(np.array(pred_subset) == np.array(gt_subset))
                n_correct = np.sum(correct_predictions)
                n_wrong = n_samples_subset - n_correct - n_refused_subset

                metrics_claim_types[claim_type] = {
                    "Accuracy": float(round(acc, 2)),
                    "Balanced_Accuracy": float(round(balanced_acc, 2)),
                    "True_Negative_Rate/Specificity": "N/A" if np.isnan(tnr) else float(round(tnr, 2)),
                    "Correct_Predictions": int(n_correct),
                    "Wrong_Predictions": int(n_wrong)
                }


        except Exception as e:
            print(f"Error computing metrics for {claim_type}: {str(e)}")
        

    return {"Claim_Type_Metrics": metrics_claim_types}



# Add a function to compute metrics on a dataset level for my datasets. Make a distinct function, instead of adding it to existing def compute_metrics to keep the code clean and understanable

def compute_metrics_dataset_level(predicted_labels: np.ndarray, ground_truth_labels: Optional[np.ndarray] = None):

    n_samples = len(predicted_labels)
    n_refused = np.count_nonzero(np.array(predicted_labels) == "REFUSED_TO_ANSWER")

    metrics = dict()
    metric_summary = {
        "Total": n_samples,
        "Refused": int(n_refused),
    }

    if ground_truth_labels is None:
        return metric_summary
    
    
    try:
        # 1) Compute metrics for dataset-level evaluation
        labels = np.unique(np.append(ground_truth_labels, predicted_labels))
        acc = accuracy_score(ground_truth_labels, predicted_labels) # added accuracy not as performance metrics, but might be relevant for uncertainty estimation evaluation (is used in expected calibration error)
        balanced_acc = balanced_accuracy_score(ground_truth_labels, predicted_labels)
        mcc = matthews_corrcoef(ground_truth_labels, predicted_labels)
        tnr = compute_tnr(ground_truth_labels, predicted_labels)
        macro_f1 = f1_score(ground_truth_labels, predicted_labels, labels=labels, average='macro')
        macro_f05 = fbeta_score(ground_truth_labels, predicted_labels, beta = 0.5, labels=labels, average = "macro")

        # 2) Absolute number of correct and wrong predictions
        correct_predictions = np.asarray(np.array(predicted_labels) == np.array(ground_truth_labels))
        n_correct_predictions = np.sum(correct_predictions)
        n_wrong_predictions = n_samples - n_correct_predictions - n_refused

        # Update metric summary with dataset-level metrics and number of correct/wrong predictions
        metric_summary.update({
            "Accuracy": float(round(acc, 2)),
            "Balanced_Accuracy": float(round(balanced_acc, 2)),
            "Matthew_Correlation_Coefficient": float(round(mcc, 2)),
            "True_Negative_Rate_Specificity": "N/A" if np.isnan(tnr) else float(round(tnr, 2)),
            "Macro_Averaged_F1_Score": float(round(macro_f1, 2)),
            "Macro_Averaged_F0.5_Score": float(round(macro_f05, 2)),
            "Correct_Predictions": int(n_correct_predictions),
            "Wrong_Predictions": int(n_wrong_predictions)
        })

    except Exception as e:
        print(f"There was an error computing dataset-level metrics: {str(e)}")

    return metric_summary


        



def compute_metrics(predicted_labels: np.ndarray,
                    ground_truth_labels: Optional[np.ndarray] = None,
                    predicted_justifications: Optional[Sequence[str]] = None,
                    ground_truth_justifications: Optional[Sequence[str]] = None,
                    is_mocheg: bool = False):
    n_samples = len(predicted_labels)
    n_refused = np.count_nonzero(np.array(predicted_labels) == "REFUSED_TO_ANSWER")

    metrics = dict()
    metric_summary = {
        "Total": n_samples,
        "Refused": int(n_refused),
        "Metrics": metrics
    }

    # Classification Metrics
    try:
        labels = np.unique(np.append(ground_truth_labels, predicted_labels))
        precision = precision_score(ground_truth_labels, predicted_labels, labels=labels, average=None)
        recall = recall_score(ground_truth_labels, predicted_labels, labels=labels, average=None)
        f1_scores = f1_score(ground_truth_labels, predicted_labels, labels=labels, average=None)

        macro_f1 = f1_score(ground_truth_labels, predicted_labels, labels=labels, average='macro')


        for label, p, r, f1 in zip(labels, precision, recall, f1_scores):
            metrics.update({
                f"{label}_Precision": float(round(p, 3)),
                f"{label}_Recall": float(round(r, 3)),
                f"{label}_F1_Score": float(round(f1, 3)),
            })

        metric_summary[f"Macro-Averaged F1-Score"] = float(round(macro_f1, 2))

    except Exception as e:
        print(f"There was an error computing classification metrics: {str(e)}")

    # Generation Metrics
    try:
        if is_mocheg and (ground_truth_justifications is not None) and (predicted_justifications is not None):
            nltk.download('punkt')

            # Load the metrics from `datasets`
            bertscore_metric = load_metric("bertscore")
            bleu_metric_datasets = load_metric("bleu")
            rouge_metric = load_metric("rouge")

            # Post-process justifications for metric computation
            processed_preds, processed_labels = postprocess_text(predicted_justifications, ground_truth_justifications)

            # Compute scores
            bleu_datasets = compute_metrics_with_text(processed_preds, processed_labels, bleu_metric_datasets, "bleu")
            bertscore = compute_metrics_with_text(processed_preds, processed_labels, bertscore_metric, "bertscore")
            rouge_scores = compute_metrics_with_text(processed_preds, processed_labels, rouge_metric, "rouge")

            # Aggregate metrics into Generation dictionary
            generation_metrics = {
                "BLEU": bleu_datasets["bleu"],
                "ROUGE1": float(rouge_scores.get("rouge1", 0)),
                "ROUGE2": float(rouge_scores.get("rouge2", 0)),
                "ROUGE_L": float(rouge_scores.get("rougeL", 0)),
                "BERTScore": bertscore["bertscore"],
            }

            # Update metric_summary with generation metrics
            metric_summary.update({"Generation": generation_metrics})

    except Exception as e:
        print(f"There was an error computing MOCHEG generation metrics: {str(e)}")

    # Final accuracy calculation
    if ground_truth_labels is not None:
        correct_predictions = np.asarray(np.array(predicted_labels) == np.array(ground_truth_labels))
        n_correct_predictions = np.sum(correct_predictions)
        n_wrong_predictions = n_samples - n_correct_predictions - n_refused
        accuracy = n_correct_predictions / (n_samples - n_refused) ## Comment out accuracy score (will not be reported anymore)

        metric_summary.update({
            "Correct": int(n_correct_predictions),
            "Wrong": int(n_wrong_predictions),
            "Accuracy": accuracy,
        })

    return metric_summary


def save_stats(stats: dict, target_dir: Path):
    """Writes two files: one machine-readable file 'stats.json' and one
    human-readable file 'stats.yaml'."""
    # Save machine-readable stats
    with open(target_dir / 'results.json', "w") as f:
        json.dump(stats, f, sort_keys=False)

    # Create a human-readable version
    stats_human_readable = stats.copy()
    stats_human_readable["Total run duration"] = sec2hhmmss(stats["Total run duration"])
    stats_human_readable["Time per claim"] = sec2mmss(stats["Time per claim"])
    """ Comment out Accuracy Score (will not be used as evaluation metrics anymore)"""
    #acc = stats["Predictions"].get("Accuracy")
    #if acc is not None:
     #   stats_human_readable["Predictions"]["Accuracy"] = f"{acc * 100:.1f} %"
    model = stats_human_readable["Model"].copy()
    model["Input tokens"] = num2text(model["Input tokens"])
    model["Output tokens"] = num2text(model["Output tokens"])
    model["Input tokens cost"] = "$" + num2text(model["Input tokens cost"])
    model["Output tokens cost"] = "$" + num2text(model["Output tokens cost"])
    model["Total cost"] = "$" + num2text(model["Total cost"])
    stats_human_readable["Model"] = model

    # Save the human-readable statistics and print them
    with open(target_dir / 'results.yaml', "w") as f:
        stats_str = yaml.dump(stats_human_readable, sort_keys=False)
        f.write(stats_str)

    print("Results:\n" + stats_str)


def fact_check(llm: str, llm_kwargs: dict,
               fact_checker_kwargs: dict, tools_config: dict,
               print_log_level: str, logging_target_dir: str | Path,
               is_averitec: bool, input_queue: Queue, output_queue: Queue, devices_queue: Queue,
               error_queue: Queue, worker_id: int):
    device_id = devices_queue.get()
    device = None if device_id is None else f"cuda:{device_id}"

    logger.set_experiment_dir(logging_target_dir)
    logger.set_log_level(print_log_level)

    # Initialize model(s)
    llm = make_model(llm, device=device, **llm_kwargs)

    tools = initialize_tools(tools_config, llm, device=device)

    # Setup fact-checker
    fc = FactChecker(
        llm=llm,
        tools=tools,
        **fact_checker_kwargs,
    )

    # Get the knowledge base object
    if is_averitec:
        searcher = tools[0]
        assert isinstance(searcher, Searcher)
        if 'averitec_kb' in searcher.search_apis:
            kb = searcher.search_apis["averitec_kb"]
            assert isinstance(kb, KnowledgeBase)
    else:
        kb = None

    # Run fact-checks as long as there is work to do
    while True:
        try:
            content = input_queue.get(timeout=10) #my adjustment: increased from 10 to 30 (avoid RateLimitErrors)
            if content is None:
                break
        except Empty:
            break

        try:

            # my addition: Adding a 5 second delay before each API call to reduce the call rate
            #time.sleep(15)

            if is_averitec and 'averitec_kb' in searcher.search_apis:
                # Restrict the KB to the current claim's resources
                kb.current_claim_id = content.id_number
            logger.set_current_fc_id(content.id_number)
            _, docs, metas = fc.check_content(content)
            doc = docs[0]
            meta = metas[0]
            output_queue.put((doc, meta))

        except Exception as e:
            error_message = f"Worker {worker_id} encountered an error while processing claim {content.id_number}:\n"
            error_message += traceback.format_exc()
            error_queue.put(error_message)

    logger.info(f"Worker {worker_id} is done and terminates gracefully.")


def load_results(path: str):
    ground_truth = []
    predictions = []
    for _, target, predicted, _ in next_result(path):
        ground_truth.append(Label[target])
        predictions.append(Label[predicted])
    return ground_truth, predictions


def next_result(path: str):
    with open(path) as f:
        reader = csv.reader(f)
        next(reader)  # skip header line
        for row in reader:
            yield row


def compute_accuracy(predictions: pd.DataFrame) -> float:
    correct_stats = predictions["correct"].value_counts()
    prediction_stats = predictions["predicted"].value_counts()
    n_refused = prediction_stats["REFUSED_TO_ANSWER"] if "REFUSED_TO_ANSWER" in list(prediction_stats.keys()) else 0
    accuracy = correct_stats[True] / (len(predictions) - n_refused)
    return accuracy


def naive_evaluate(model: str, model_kwargs: dict = None, benchmark_name: str = "fever1", n_samples: int = None,
                   **kwargs) -> float:
    benchmark = load_benchmark(benchmark_name)
    model = make_model(model, **model_kwargs)
    samples_to_evaluate = benchmark[:n_samples] if n_samples else benchmark

    eval_log = []
    predictions = []
    for instance in samples_to_evaluate:
        query = f"Check if the following claim is 'supported', 'not enough information', or 'refuted' using your available knowledge. Answer with only one of the three options. Claim: {instance['content']}"
        prediction = model.generate(query).replace("'", "").replace(".", "").lower()
        if prediction not in ['supported', 'not enough information', 'refuted']:
            print(instance["id"], prediction)
        eval_log.append({"claim": instance["content"], "pred_label": prediction})
        prediction_is_correct = instance["label"].value == prediction
        predictions.append(prediction_is_correct)
    accuracy = np.average(predictions)

    return accuracy, eval_log


def bold_print_dict(dictionary: dict):
    for key, value in dictionary.items():
        print(f"\t{bold(str(key))}: {value}")


def postprocess_text(preds, labels, num_limit=None):
    """
    Postprocessing for BERTScore evaluation for MOCHEG dataset
    """
    if num_limit:
        preds = [TreebankWordDetokenizer().detokenize(pred.split()[:num_limit]) for pred in preds]
    preds = ["\n".join(nltk.sent_tokenize(pred.strip())) for pred in preds]
    labels = ["\n".join(nltk.sent_tokenize(label.strip())) for label in labels]
    return preds, labels


def remove_urls_and_brackets(text):
    if pd.isna(text):
        return ''
    else:
        return re.sub(r'\[.*?\]\(.*?\)', '', text)


def compute_metric_with_text_bleu(decoded_preds, decoded_labels, metric):
    decoded_preds, decoded_labels = postprocess_text(decoded_preds, decoded_labels)
    decoded_preds_bleu = [pred.split(' ') for pred in decoded_preds]
    decoded_labels_bleu = [[pred.split(' ')] for pred in decoded_labels]
    result = metric.compute(predictions=decoded_preds_bleu, references=decoded_labels_bleu)
    result["bleu"] = round(result["bleu"] * 100, 4)
    return result


def compute_metric_with_text_bertscore(decoded_preds, decoded_labels, metric):
    decoded_preds, decoded_labels = postprocess_text(decoded_preds, decoded_labels)
    all_result = metric.compute(predictions=decoded_preds, references=decoded_labels, lang="en")
    avg_result = sum(all_result["f1"]) / len(all_result["f1"]) * 100
    return {"bertscore": round(avg_result, 4)}


def compute_metrics_with_text(decoded_preds, decoded_labels, metric, metric_name):
    if metric_name == "bleu":
        return compute_metric_with_text_bleu(decoded_preds, decoded_labels, metric)
    elif metric_name == "bertscore":
        return compute_metric_with_text_bertscore(decoded_preds, decoded_labels, metric)
    else:
        decoded_preds, decoded_labels = postprocess_text(decoded_preds, decoded_labels)
        result = metric.compute(predictions=decoded_preds, references=decoded_labels, use_stemmer=True)
        result = {key: round(value.mid.fmeasure * 100, 4) for key, value in result.items()}
        return result
