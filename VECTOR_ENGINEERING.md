# Vector Engineering - Search, Indexing, and Reranking Specification

This document details the vector database configurations, embedding generators, retrieval operations, and re-ranking algorithms implemented in **AskGovRAGBot**.

---

## 1. Vector Database Architecture & Free Tiers

To avoid Python 3.14 C++ compilation issues with Chroma, the project supports a dual-engine architecture using **Pinecone** and **Qdrant**. Their client libraries are pure Python and require no local binary compiler setup.

### A. Pinecone (Cloud Tier)
* **Starter Free Tier**: Permitted to run exactly **1 Index** with up to **100,000 vectors**.
* **Understanding "1 Index"**: An index is a logical vector database table. It locks in the vector dimension size (e.g. 1024 for Cohere/BGE) and the distance metric (e.g. Cosine Similarity). One index is all that is required for AskGovRAGBot; different document domains are separated using metadata filters within this single index.
* **Understanding "100,000 Vectors"**: A vector represents one indexed chunk of text (e.g. one policy section). Our mock policy corpus has only 15 sections. A limit of 100,000 vectors allows us to store up to **5,000 to 10,000 full pages of text** in the free tier, letting this system scale easily from a prototype to a mid-sized corporate directory.

### B. Qdrant (Local Fallback)
* **Local Disk Storage**: Rather than running in-memory or requiring a cloud account, Qdrant runs locally on your Mac's filesystem by saving data directly to a disk path (similar to SQLite). 
* **Integration**: When `VECTOR_STORE=chroma` is toggled off, we use Qdrant locally (`langchain-qdrant`), maintaining standard LangChain retrieval code.

---

## 2. Governed Hybrid Search (Oracle Cosine Analogy)

In your original NetSuite Helidon architecture, you utilized Oracle DB JDBC cosine similarity distance queries filtered by the user's role context. In AskGovRAGBot, we implement **Governed Hybrid Search** mimicking that behavior:

```
                  ┌───────────────────────────────┐
                  │          User Query           │
                  └───────────────┬───────────────┘
                                  │
                  ┌───────────────┴───────────────┐
                  │     Security & Auth check     │
                  │   Infers User Permission (1-4)│
                  └───────────────┬───────────────┘
                                  │
            ┌─────────────────────┴─────────────────────┐
            ▼                                           ▼
┌───────────────────────┐                   ┌───────────────────────┐
│ Dense Semantic Search │                   │  Sparse Keyword Search│
│   (Cosine Distance)   │                   │        (BM25)         │
└───────────┬───────────┘                   └───────────┬───────────┘
            │                                           │
            │  Filter: min_permission_level <= user_lvl │
            └─────────────────────┬─────────────────────┘
                                  │
                    ┌─────────────┴─────────────┐
                    │    Reciprocal Rank Fusion │
                    │        RRF Scoring        │
                    └─────────────┬─────────────┘
                                  │
                    ┌─────────────┴─────────────┐
                    │      Reranking Node       │
                    │ (Cohere / Gemini Reranker)│
                    └─────────────┬─────────────┘
                                  ▼
                    ┌───────────────────────────┐
                    │   Top-K context for LLM   │
                    └───────────────────────────┘
```

1. **Dense Semantic Search (Cosine)**: Computes vector distance between the query embedding and document embeddings.
2. **Sparse Keyword Search (BM25)**: Standard token-matching. Ensures that exact numeric codes (like `HR-101`) or key terms are matched even if semantic vector similarity is weak.
3. **Role-Gating Metadata Filter**: Enforces access boundaries inside the DB query (e.g., `WHERE min_permission_level <= user_permission`), filtering candidates before vector distance matches are compiled.
4. **RRF & Rerank**: Combines Dense and Sparse ranks, prioritizing documents that excel in both.

---

## 3. Caching & Persistence Strategies

To cut API costs and provide 0ms latency for repetitive queries, we implement two persistent caching layers inside our SQLite governance ledger:

### A. Local Embedding Cache (SQLite)
* **Workflow**:
  1. The user asks: *"What is the hybrid work policy?"*
  2. The system checks the `embedding_cache` table in SQLite for the query string.
  3. If a record is found, it loads the 1024-dimension float list from database memory (0ms latency, $0 cost).
  4. If not found, it calls the Cohere/OpenAI Embedding API, gets the vector, and saves it to SQLite for future runs.

### B. LLM Completion Cache (SQLite)
* **Workflow**:
  1. Exact-match queries (e.g. repeated greetings or standard help checks) are cached in the `llm_cache` table based on a hash of the combined state prompt.
  2. If the user repeats a query within the same session parameters, the cached string is returned instantly.

---

## 4. Reranking Algorithms

The Reranking node evaluates the raw retrieved chunks, sorting them by semantic relevance. We support two adapters:

### A. Cohere Reranker (Production Standard)
* Uses the `langchain-cohere` module.
* Connects to Cohere's `rerank-english-v3.0` API. 
* Evaluates the top-k database matches and assigns a relevance score between 0.0 and 1.0. Chunks scoring below `0.65` are truncated.

### B. Gemini Reranker Node (Zero-Key Local Fallback)
If no Cohere API key is provided, the LangGraph workflow routes to a custom LLM reranker node. The node queries Gemini Flash using a scoring template:

```
[SYSTEM PROMPT]
You are a relevance auditor. Rate how relevant the provided document chunk is to answering the user query. Output a score between 0 and 100.

[USER QUERY]
{query}

[DOCUMENT CHUNK]
{chunk}

[OUTPUT FORMAT]
Output a single integer representing the relevance score.
```
Any chunk scoring below `70` is dropped, ensuring that only highly relevant data is augmented into the generation prompt.
