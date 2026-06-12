# Ingestion Knowledge Base - Component Roles & Architecture

This document clarifies the design roles, definitions, and workflows of the policy database ingestion system in **AskGovRAGBot**.

---

## 1. The 3 Ingestion Roles

To ingest and index our files, we separate the process into three distinct responsibilities following the **Single Responsibility Principle (SRP)**:

### Step A: `DocumentParser` (The Chunker)
* **What it does**: It reads a raw file format from disk, extracts text sections, and divides them into semantic chunks. It does **not** generate vectors or touch the database.
* **Example**:
  1. `XmlPolicyParser` reads `hr_policy.xml`.
  2. It splits the document at every `<section>` tag.
  3. It returns a list of raw text strings (chunks) and dictionary objects (metadata like `min_permission_level=2`).

### Step B: `VectorDatabaseIndexer` (The Embedder & Saver)
* **What it does**: It takes the raw text chunks and metadata, calls the embedding model (to turn text into floating-point numbers/vectors), and stores them directly inside Chroma/Pinecone.
* **Example**:
  1. It receives a text chunk: *"Full-time employees accrue 15 days of PTO..."*.
  2. It calls our embedding model (e.g., Cohere/BGE) to get a 1024-dimension vector.
  3. It executes a database write, saving the **text + vector + metadata** into the Vector DB index.

### Step C: `DocumentIngestionPipeline` (The Coordinator)
* **What it does**: It is the director. It doesn't parse text or index databases directly. It simply reads the list of raw files on disk, routes them to the correct parser, and hands the output chunks to the indexer.
* **Example**:
  1. The pipeline looks at `data/`. It sees `hr_policy.xml` (XML) and `it_security_policy.json` (JSON).
  2. It sends `hr_policy.xml` to `XmlPolicyParser`.
  3. It sends `it_security_policy.json` to `JsonPolicyParser`.
  4. It collects all the resulting chunks and sends them to the `VectorDatabaseIndexer` to write to the database.

---

## 2. Naming Refinements & SOLID Mappings

* **PII Governance**: The security masking class is named **`SecurityMaskingService`** (with comments detailing its role as a `PiiGovernanceManager`).
* **Parsers**:
  * `DocumentParser` (Base parsing strategy contract)
  * `XmlPolicyParser` (XML policy parser/chunker)
  * `JsonPolicyParser` (JSON policy parser/chunker)
* **Database & Orchestration**:
  * `VectorDatabaseIndexer` (Embeds chunks and stores them to DB)
  * `DocumentIngestionPipeline` (Coordinates the file-to-db flow)
* **Script Location**: Saved at **`scripts/ingest_policies_db.py`**.

---

## 3. Tag-Based Chunks vs. Naive Semantic Chunking

In **AskGovRAGBot**, we use **Tag-Based Chunks** rather than naive sliding-window semantic splits.

### Naive Semantic Chunking
* **Method**: Splits documents based on formatting delimiters (like double newlines, sentence gaps, or word lengths).
* **Limitations**: It is blind to document structure. If a corporate policy has a list or table, naive semantic chunking can split right in the middle of a vital key-value pair, leading to fragmented context when read by the LLM.

### Tag-Based Chunking (Our Approach)
* **Method**: Reads the document structure and splits it precisely at the tags defined by the author (e.g., `<section>` elements in XML, or key elements in JSON).
* **Key Benefits**:
  1. **Zero Sentence Fracturing**: The policy sections are guaranteed to stay intact, providing complete paragraphs to the LLM during QA synthesis.
  2. **Deterministic Metadata Mapping**: Metadata parameters (such as `min_permission_level=2` for employee policies) are extracted directly from the tags and bound to the vector index. This ensures bulletproof access control.

