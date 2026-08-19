# Athletic Supplements RAG System Evaluation Guide

This document describes the evaluation framework for the **Athletic Supplements RAG System**. The evaluation suite, located in the [evaluation/](file:///d:/Omar/Programming/AI_Projects/Orange_Instant_Hackathon/athletic-suppliments-RAG/evaluation/) directory, is a dedicated test harness designed to grade and diagnose the pipeline's retrieval and answering performance against a curated golden dataset.

---

## 1. Project Overview

The project is a localized, high-precision Retrieval-Augmented Generation (RAG) system targeting the NIH ODS (Office of Dietary Supplements) fact sheet: **"Dietary Supplements for Exercise and Athletic Performance"**. 

To provide professional, accurate answers, the project structures RAG pipeline tasks into distinct modules (`fetch ➔ clean ➔ chunk ➔ augment ➔ embed ➔ index ➔ retrieve ➔ answer`). 

### Why Evaluate?
RAG pipelines have many moving parts (chunk sizes, retrieval depths, query expansion techniques, prompting strategies). Tweaking any of these settings affects response quality. The evaluation suite provides a scientific, metric-driven approach to measure the impact of changes.

---

## 2. The Evaluation Folder Structure

The [evaluation/](file:///d:/Omar/Programming/AI_Projects/Orange_Instant_Hackathon/athletic-suppliments-RAG/evaluation/) module mirrors the functional structure of the core pipeline:

```
evaluation/
├── __init__.py           # Package exports and documentation
├── __main__.py           # CLI routing (`python -m evaluation ...`)
├── cli.py                # Command-line interface parser and runner
├── dataset_loader.py     # Loader supporting JSON, JSONL, and CSV golden sets
├── diagnostics.py        # Automated recommendation & LLM-powered root-cause analysis
├── evaluate_rag.py       # Ragas metrics engine with acronym normalization
├── harness.py            # Execution coordinator (runs questions through the pipeline)
├── report.py             # CLI formatting and JSON disk reports
└── data/
    └── golden_dataset.json  # Shipped evaluation dataset (30 golden QA pairs)
```

---

## 3. Core Evaluation Metrics

The framework leverages **Ragas** (Retrieval Augmented Generation Assessment) to compute four distinct metrics, separating retrieval failures from generation failures:

| Metric | Phase | Focus | Description |
| :--- | :--- | :--- | :--- |
| **`context_recall`** | `Retriever` | Retrieval | Did retrieval find the evidence the reference answer relies on? |
| **`context_precision`** | `Retriever` | Retrieval | Are the retrieved chunks actually relevant to the question? |
| **`faithfulness`** | `Answerer` | Generation | Is the generated answer grounded in the retrieved chunks? (Detects hallucinations) |
| **`answer_relevancy`** | `Answerer` | Generation | Does the answer directly address the user's question? |

---

## 4. Acronym Normalization

Clinical and athletic documentation frequently switches between acronyms (e.g., `HMB`, `BCAAs`, `ATP`) and their full chemical expansions (e.g., `beta-hydroxy beta-methylbutyrate`). 

To prevent the evaluation judge from penalizing correct answers due to synonym differences:
* The system utilizes `normalize_medical_text()` in [evaluate_rag.py](file:///d:/Omar/Programming/AI_Projects/Orange_Instant_Hackathon/athletic-suppliments-RAG/evaluation/evaluate_rag.py).
* It replaces acronyms with their expanded representations before grading, ensuring a terminology-agnostic assessment.

---

## 5. Module Breakdown & System Flow

When running an evaluation via `python -m evaluation run`, the system executes the following steps:

```
[ Golden Dataset ] ➔ dataset_loader.py (loads & normalizes)
                           ⬇
[ Harness Execution ] ➔ harness.py (runs questions through RAG pipeline)
                           ⬇
[ Metric Evaluation ] ➔ evaluate_rag.py (runs RAGAS using a model judge)
                           ⬇
[ Diagnostics Engine ] ➔ diagnostics.py (rule-based + LLM root-cause analysis)
                           ⬇
[ Reporting Stage ] ➔ report.py (writes JSON report & outputs ANSI CLI table)
```

### A. Dataset Loading & Key Normalization
* **File:** [dataset_loader.py](file:///d:/Omar/Programming/AI_Projects/Orange_Instant_Hackathon/athletic-suppliments-RAG/evaluation/dataset_loader.py)
* **Description:** Reads dataset files (`.json`, `.jsonl`, `.csv`). It automatically maps keys (like mapping `reference_answer` in [golden_dataset.json](file:///d:/Omar/Programming/AI_Projects/Orange_Instant_Hackathon/athletic-suppliments-RAG/evaluation/data/golden_dataset.json) to `ground_truth` required by Ragas). It preserves other metadata while stripping pre-baked outputs to ensure the pipeline is evaluated fresh.

### B. The Evaluation Harness
* **File:** [harness.py](file:///d:/Omar/Programming/AI_Projects/Orange_Instant_Hackathon/athletic-suppliments-RAG/evaluation/harness.py)
* **Description:** Iterates through the loaded dataset. For each question, it performs `pipeline.search()` and `pipeline.answer()`. It checks if the system is ready (e.g., asserts that the ChromaDB collection is not empty, and the pipeline is online/answering is active) before executing.

### C. The Scoring Engine
* **File:** [evaluate_rag.py](file:///d:/Omar/Programming/AI_Projects/Orange_Instant_Hackathon/athletic-suppliments-RAG/evaluation/evaluate_rag.py)
* **Description:** Feeds the collected outputs to the Ragas scoring library. It configures the evaluation LLM endpoint (by default, pointing to the local LM Studio endpoint or a designated evaluation judge).

### D. Automated Diagnostics
* **File:** [diagnostics.py](file:///d:/Omar/Programming/AI_Projects/Orange_Instant_Hackathon/athletic-suppliments-RAG/evaluation/diagnostics.py)
* **Description:** Analyzes samples that score below the threshold (default: `0.8`).
  1. **Rule-Based Suggestions:** Suggests immediate engineering fixes (e.g., tweaking `top_k`, adjusting chunk overlap, or adding strict citation prompts).
  2. **LLM-Powered Analysis:** Re-prompts the LLM as a "Clinical Review Board" to evaluate the failed sample and generate a free-form root-cause analysis.

### E. Reporting
* **File:** [report.py](file:///d:/Omar/Programming/AI_Projects/Orange_Instant_Hackathon/athletic-suppliments-RAG/evaluation/report.py)
* **Description:** Outputs a detailed, timestamped JSON report inside [eval_results/](file:///d:/Omar/Programming/AI_Projects/Orange_Instant_Hackathon/athletic-suppliments-RAG/eval_results/) and prints a beautiful color-coded summary directly in the CLI terminal.

---

## 6. How to Run & Configure

### Prerequisites
Make sure dependencies are installed:
```bash
.venv/bin/pip install -r requirements.txt
```

Before running evaluation, you must first build the vector index:
```bash
python -m rag.cli build
```

### CLI Command
To run the evaluation:
```bash
python -m evaluation run
```

### Command Overrides
You can customize the evaluation run using CLI arguments:
* **Change Dataset:** `--dataset path/to/dataset.csv`
* **Custom Acceptability Threshold:** `--threshold 0.75`
* **Disable LLM Diagnostics** (skips slow LLM analysis calls): `--no-llm-diagnostics`
* **Specify External Judge Model:** `--eval-model gpt-4o --eval-base-url https://api.openai.com/v1`
* **Evaluate at Specific Depth:** `--top-k 3`

---

## 7. Evaluation Feature Checklist Mapping

Here is how the project addresses each specific evaluation requirement:

### 📋 Golden Dataset
* **Questions:** Stored in the `"question"` key of [golden_dataset.json](file:///d:/Omar/Programming/AI_Projects/Orange_Instant_Hackathon/athletic-suppliments-RAG/evaluation/data/golden_dataset.json).
* **Reference Answers:** Stored in the `"reference_answer"` key (automatically mapped to `"ground_truth"` inside [dataset_loader.py](file:///d:/Omar/Programming/AI_Projects/Orange_Instant_Hackathon/athletic-suppliments-RAG/evaluation/dataset_loader.py)).
* **Relevant/Gold Chunk IDs:** Included as the `"relevant_chunks"` placeholder list in the dataset.
* **Question Categories/Types:** Grouped and analyzed during the diagnostics step in [diagnostics.py](file:///d:/Omar/Programming/AI_Projects/Orange_Instant_Hackathon/athletic-suppliments-RAG/evaluation/diagnostics.py).

### 🔍 Retrieval Evaluation
* **Recall@K & Precision@K:** Measured directly via Ragas (`context_recall` and `context_precision`) in [evaluate_rag.py](file:///d:/Omar/Programming/AI_Projects/Orange_Instant_Hackathon/athletic-suppliments-RAG/evaluation/evaluate_rag.py).
* **MRR & Hit Rate:** The evaluation harness parses and evaluates ranks using the retrieval depth `top_k` configuration.
* **Saving Retrieved Chunk IDs / Distances:** Extracted and stored for every query (fields include `chunk_id`, `section`, `similarity` vector distance, and boosted `score`) by the harness in [harness.py](file:///d:/Omar/Programming/AI_Projects/Orange_Instant_Hackathon/athletic-suppliments-RAG/evaluation/harness.py).

### 🧠 End-to-End RAG/LLM Evaluation
* **Retrieved Context:** Extracted live via similarity search during the run.
* **Generated Answer:** Generated dynamically by the answering model during the evaluation run.
* **Reference Answer:** Loaded from the dataset and passed to Ragas as the ground truth.
* **Faithfulness & Answer Relevance:** Graded using the Ragas library's LLM metrics.
* **Correctness:** Assessed by cross-comparing generated answers against reference answers with acronym expansion disabled/enabled.

### 🧪 Multiple LLM Experiments
* **Model Name / Version / Parameters:** Recorded inside the `Settings` dataclass and outputted in JSON reports.
* **Persistent Evaluation Results:** Saved with unique UTC timestamps (`eval_report_YYYYMMDD_HHMMSS.json`) in the [eval_results/](file:///d:/Omar/Programming/AI_Projects/Orange_Instant_Hackathon/athletic-suppliments-RAG/eval_results/) directory, ensuring one run does not overwrite another.
* **Experiment Comparisons:** Results are saved in clean structured JSON formatting for easy comparison.

### 🚀 Evaluation Runner
* Run the evaluation runner automatically using:
  ```bash
  python -m evaluation run --eval-model <model_name> --eval-base-url <url>
  ```
  This integrates directly with the existing `RAGPipeline` and doesn't require a separate system.

