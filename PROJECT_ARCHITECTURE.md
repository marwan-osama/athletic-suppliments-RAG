# Athletic Supplements RAG System Architecture & Technical Specifications

This document provides a comprehensive overview of the design, system flow, codebase structure, and technical implementation details of the Athletic Supplements Retrieval-Augmented Generation (RAG) system. It serves as a blueprint for both human developers and AI assistants to quickly understand the system's architecture.

---

## 1. System Overview & Goal
The project implements a localized, high-precision RAG pipeline over the NIH ODS (Office of Dietary Supplements) fact sheet: **"Dietary Supplements for Exercise and Athletic Performance"**. 

Instead of treating the document as flat text, the system uses a structured pipeline that parses the HTML/URL source, cleans it, segments it by supplement topics, generates hypothetical questions for better semantic matching, indexes it into ChromaDB, and retrieves grounded chunks to answer user queries with precise citations.

---

## 2. Pipeline Architecture
The pipeline is designed using a functional composition pattern where each stage is a class/callable composing with the pipe (`|`) operator.

```
[ Build Phase ]
Source (HTML/URL) ➔ SourceFetcher ➔ MarkdownCleaner ➔ MarkdownChunker 
                                                               ⬇
                                                     QuestionGenerator (LLM)
                                                               ⬇
  ChromaDB Index ➔ VectorIndex ➔ ServerEmbedder (Embed Model) ⬶┛

[ Query & Answer Phase ]
User Query ➔ Retriever (Similarity Match) ➔ Chunk Deduplicator ➔ Answerer (LLM) ➔ Citation Output
```

### Build Pipeline (Data Indexing)
1. **SourceFetcher:** Resolves the source (URL or local HTML) and converts it to clean Markdown using `trafilatura`. Results are cached locally in `.cache/`.
2. **MarkdownCleaner:** Strips citation links, navigation links, reference lists, and restores empty heading names from context.
3. **MarkdownChunker:** Splices Markdown based on heading boundaries (supplement topics). Prefixes each chunk text with its heading hierarchy path (`Creatine > Efficacy`) to retain local context.
4. **QuestionGenerator:** Spawns a parallel thread pool of LLM completion queries to generate hypothetical questions for each chunk (e.g., 3 questions per chunk) to optimize asymmetric semantic search.
5. **ServerEmbedder:** Batches the chunks and questions, formats them with asymmetric instruction prefixes (`title: none | text: ` for documents), and embeds them.
6. **VectorIndex:** Inserts the vector embeddings into a ChromaDB database collections named dynamically based on the current chunking and model configuration.

### Query Pipeline (Search & Generation)
1. **User Query:** The query is formatted with the search instruction prefix (`task: search result | query: `).
2. **Retriever:** Queries ChromaDB for the closest vector matches against both raw chunks and generated questions.
3. **Deduplicator:** Group retrieved matches by the parent chunk ID so that a single source section does not crowd out other relevant context.
4. **Answerer:** Formulates a prompt combining the query and retrieved context, sends it to the LLM, and produces a grounded response with numerical citations (e.g., `[1]`, `[2]`).

---

## 3. Codebase Structure & Components

All core logic resides in the [rag/](file:///d:/Omar/Programming/AI_Projects/Orange_Instant_Hackathon/athletic-suppliments-RAG/rag/) package:

| File | Primary Class | Purpose |
| :--- | :--- | :--- |
| [rag/fetching.py](file:///d:/Omar/Programming/AI_Projects/Orange_Instant_Hackathon/athletic-suppliments-RAG/rag/fetching.py) | `SourceFetcher` | Pulls HTML and converts it to Markdown. Caches raw content locally. |
| [rag/preprocessing.py](file:///d:/Omar/Programming/AI_Projects/Orange_Instant_Hackathon/athletic-suppliments-RAG/rag/preprocessing.py) | `MarkdownCleaner` | Cleans up markdown markup, removes reference sections, and parses empty headings into supplement names. |
| [rag/chunking.py](file:///d:/Omar/Programming/AI_Projects/Orange_Instant_Hackathon/athletic-suppliments-RAG/rag/chunking.py) | `MarkdownChunker` | Handles heading-aware text splitting. |
| [rag/augmentation.py](file:///d:/Omar/Programming/AI_Projects/Orange_Instant_Hackathon/athletic-suppliments-RAG/rag/augmentation.py) | `QuestionGenerator` | Uses the LLM in parallel threads to generate hypothetical questions. |
| [rag/llm.py](file:///d:/Omar/Programming/AI_Projects/Orange_Instant_Hackathon/athletic-suppliments-RAG/rag/llm.py) | `LLMClient` | The sole client communicating with the OpenAI-compatible endpoint. Implements retries, rate-limiting, and error handling. |
| [rag/embedding.py](file:///d:/Omar/Programming/AI_Projects/Orange_Instant_Hackathon/athletic-suppliments-RAG/rag/embedding.py) | `ServerEmbedder` / `HashEmbedder` | Generates vector embeddings (with offline fallback). |
| [rag/indexing.py](file:///d:/Omar/Programming/AI_Projects/Orange_Instant_Hackathon/athletic-suppliments-RAG/rag/indexing.py) | `VectorIndex` | Interacts with ChromaDB to store/reset embeddings. |
| [rag/retrieval.py](file:///d:/Omar/Programming/AI_Projects/Orange_Instant_Hackathon/athletic-suppliments-RAG/rag/retrieval.py) | `Retriever` | Fetches nearest neighbors and groups them to avoid duplicate overlap. |
| [rag/answering.py](file:///d:/Omar/Programming/AI_Projects/Orange_Instant_Hackathon/athletic-suppliments-RAG/rag/answering.py) | `Answerer` | Compiles prompt template and calls the LLM to get the final cited response. |
| [rag/config.py](file:///d:/Omar/Programming/AI_Projects/Orange_Instant_Hackathon/athletic-suppliments-RAG/rag/config.py) | `Settings` | Consolidated dataclass managing all pipeline hyper-parameters and environment loading. |
| [rag/pipeline.py](file:///d:/Omar/Programming/AI_Projects/Orange_Instant_Hackathon/athletic-suppliments-RAG/rag/pipeline.py) | `RAGPipeline` | Orchestrator connecting all components. |
| [rag/cli.py](file:///d:/Omar/Programming/AI_Projects/Orange_Instant_Hackathon/athletic-suppliments-RAG/rag/cli.py) | - | CLI command parser (`chunks`, `build`, `query`). |
| [app.py](file:///d:/Omar/Programming/AI_Projects/Orange_Instant_Hackathon/athletic-suppliments-RAG/app.py) | - | Streamlit Frontend Web App. |

---

## 4. Key Architectural & Design Decisions

### 1. Asymmetric Embeddings & Prefixes
Asymmetric embedding models (like `embeddinggemma`) perform significantly better when query/document instruction templates are prepended during generation.
* **Document Chunks Prefix:** `title: none | text: `
* **User Queries Prefix:** `task: search result | query: `

### 2. Content-Derived Stable IDs
Instead of utilizing randomized UUIDs (e.g. `uuid4`), the pipeline generates deterministic content hashes (`c0042-1f3a9b7c`) based on chunk contents. This enables idempotent `upsert` operations: rebuilding the index updates existing records in ChromaDB rather than duplicating them.

### 3. Heading-Aware Chunking & Path Preservation
Chunks are split at logical markdown heading boundaries rather than arbitrary character cuts. Each chunk is prefixed with its hierarchy path (`Creatine > Efficacy`). If a heading is parsed as blank by `trafilatura`, the system recovers the supplement name from the first sentence (e.g. "HMB is a..." -> `HMB`).

### 4. Collection Versioning (Naming Conventions)
ChromaDB collections are named dynamically based on parameters that affect vector dimensions or content. If you change a parameter (e.g., chunk size, overlap, or the embedder model), the pipeline builds/accesses a separate collection:
`ods_health_facts__{embedder_tag}_c{chunk_size}_o{overlap}_q{questions_count}_m{min_chars}_s{prepend_section}`
This prevents mixing mismatched indices and avoids unnecessary rebuilding.

---

## 5. Configuration & Environment Settings

The RAG pipeline is configured via a local `.env` file (copied from `.env.example`). Key options include:

* `LLM_BASE_URL`: Base endpoint of the OpenAI-compatible API (e.g. `http://localhost:11434/v1` for Ollama, or LM Studio's endpoint).
* `LLM_API_KEY`: API key for the endpoint (e.g., `ollama` or OpenRouter keys).
* `EMBED_MODEL`: Model identifier for text embeddings.
* `LLM_MODEL`: Model identifier for question generation and answering.
* `RAG_ENABLE_QUESTIONS`: Set to `true` to generate hypothetical questions per chunk (significantly improves retrieval, but increases build time) or `false` to disable.
* `RAG_OFFLINE`: Set to `true` to skip model servers entirely and run retrieval using word-overlap vectors (`HashEmbedder`).

---

## 6. Execution Commands

### Streamlit UI Dashboard
Starts the interactive frontend interface for querying and visualizing chunk statistics:
```bash
.venv/bin/streamlit run app.py
```

### CLI Operations
* **Inspect Chunks offline:**
  ```bash
  .venv/bin/python -m rag.cli chunks --dump chunks_dump.md
  ```
* **Build / Rebuild the Index:**
  ```bash
  .venv/bin/python -m rag.cli build --force
  ```
* **Query the index & get cited answer:**
  ```bash
  .venv/bin/python -m rag.cli query "Does creatine improve athletic performance?" --answer
  ```

### Evaluation CLI Operations
* **Run complete pipeline evaluation:**
  ```bash
  .venv/bin/python -m evaluation run
  ```
* **Run evaluation with config overrides (e.g. custom threshold and external judge LLM):**
  ```bash
  .venv/bin/python -m evaluation run --threshold 0.75 --eval-model gpt-4o --eval-base-url https://api.openai.com/v1
  ```

