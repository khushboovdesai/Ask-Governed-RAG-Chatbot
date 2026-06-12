# AskGovRAGBot Telemetry & Metrics Manual

This document details the multi-layered observability architecture of the AskGovRAGBot system, covering database metrics, application metrics, advanced LLM latency indicators, token usage tracking, RAG semantic quality scores, and cloud infrastructure billing.

---

## 🗄️ 1. Database (DB) Metrics Overview

Database metrics monitor the health, performance, and capacity of both your semantic vector search database and your local transaction ledger.

### Who Collects Database Metrics?
* **For Local Databases (SQLite, Chroma DB)**: The application backend collects database execution metrics (such as query duration or connection pool state). Host-level monitors (like Prometheus node-exporter) track SQLite database file size and read/write disk I/O.
* **For Cloud Vector Databases (Pinecone, Qdrant)**: The cloud database service collects metrics natively on its server infrastructure and displays them on its cloud console.

### What Do Cloud Vector DB Metrics Look Like?
* **Index Size**: Total disk space occupied (e.g., `45.2 MB`).
* **Vector Count**: The total number of chunks embedded and indexed (e.g., `1,250 vectors`).
* **Query Search Latency (p50, p90, p99)**: The duration of the vector similarity calculation (e.g., `p95 latency = 12ms`).
* **Write/Ingest Throughput**: Vectors inserted per second during seeding (e.g., `85 vectors/sec`).
* **Active Connections / IOPS**: Number of concurrent API connection requests.

---

## ⏱️ 2. Advanced LLM Latency & Cost Metrics

These metrics monitor the latency profile of your generation engine and track real-time operational costs.

### A. TTFT (Time to First Token)
* **What it is**: The time elapsed between the client sending the request and the model generating the very first token.
* **Significance**: This is the primary indicator of **perceived responsiveness** in streaming systems. 
* **How it's tracked**: Measured by tracking the delta between request start time and the first yield from the streaming generator API.
* **Where to monitor**: Promoted to Prometheus histograms or reviewed in the **LangSmith Run Details** latency tracker.

### B. TTLT (Time to Last Token / Generation Time)
* **What it is**: The time elapsed between the generation of the first token and the final completion token (marking the end of generation).
* **Significance**: Measures the model's generation throughput (tokens per second).
* **How it's tracked**: Calculated as `Total Request Latency - TTFT`.
* **Where to monitor**: Exposed to Prometheus/Grafana or tracked in LangSmith runs.

### C. Token Usage (Cost Management)
* **What it is**: The exact count of input (prompt) tokens and output (completion) tokens.
* **Significance**: Direct mapping to external API billing expenditures.
* **How it's tracked**: Extracted from the API response metadata dictionary returned by providers (Cohere, Gemini, OpenAI).
* **Where to monitor**:
  * **LangSmith**: Displayed in the metadata panel (`prompt_tokens`, `completion_tokens`, `total_tokens`) for every chain run.
  * **Prometheus**: Exposed via custom counters (e.g. `askgovragbot_tokens_total{role="Manager", type="prompt"}`).

---

## 🎯 3. RAG Semantic Quality Metrics

Semantic metrics analyze the quality, accuracy, and truthfulness of the retrieved context and generated answers.

### A. Faithfulness (Groundedness)
* **What it is**: Measures whether the generated response is entirely derived from, and supported by, the retrieved source document segments (no hallucinations).
* **How it's tracked**:
  * **Offline Evaluation**: The evaluator suite (`scripts/evaluate.py`) computes a mathematical score using Ragas by checking context statements against generated sentences.
  * **Online Evaluation**: The `output_guardrail_node` acts as a real-time LLM-as-a-judge, returning a groundedness score (0.0 to 1.0) and blocking response presentation if the score is `< 0.8`.
* **Where to monitor**: LangSmith Feedback panels, SQLite logs (`audit_trail` table), or Prometheus.

### B. Answer Relevancy
* **What it is**: Measures how well the generated answer addresses the user's initial question (no rambling or off-topic responses).
* **How it's tracked**: Computed during offline evaluation runs using Ragas. The judge LLM generates multiple query variations based on the response and checks their similarity to the original query.
* **Where to monitor**: LangSmith evaluation projects or output reports.

---

## 📊 4. Multi-Layer Telemetry & Metrics Matrix

| Layer | Metric Name / Indicator | What It Tracks | Example Value | Where to Monitor |
| :--- | :--- | :--- | :--- | :--- |
| **Cloud Provider / Infrastructure** | Nebius GPU Computing Cost | Dollar cost and GPU node execution hours. | `$12.45 spent` | **Nebius Billing Console** |
| | Token Usage per API Key | Total prompt + completion tokens consumed by role-scoped keys. | `152,400 input tokens` | **Nebius / OpenAI Dashboard** |
| **Database & Vector DB** | Vector Count | Total indexed document vector segments. | `450 vectors` | **Pinecone Cloud Console** |
| | DB Query Search Latency | Time to perform semantic similarity matching. | `14ms` | **Pinecone Console** / custom APM |
| | Storage File Size | Disk space consumed by SQLite ledger. | `2.4 MB` | **Host Node Exporter** / CLI |
| **Application Layer (FastAPI)** | `askgovragbot_api_requests_total` | Total HTTP requests split by **endpoint** and **user role**. | `45 requests (role=Manager)` | **Prometheus Dashboard** (`:9090`) |
| | `askgovragbot_request_duration_seconds` | End-to-end API response latency histogram. | `p90 = 4.2 seconds` | **Prometheus Dashboard** (`:9090`) |
| | `askgovragbot_pii_masked_total` | Total count of PII tokens sanitized in-flight. | `12 names, 2 SSNs` | **Prometheus Dashboard** (`:9090`) |
| | `askgovragbot_hallucinations_detected_total` | Count of generated answers failing groundedness checks. | `3 blocks` | **Prometheus Dashboard** (`:9090`) |
| **LLM & RAG Metrics** | **TTFT (Time to First Token)** | Time to generate the first token of a streaming response. | `450ms` | **LangSmith UI** / **Prometheus** |
| | **TTLT (Time to Last Token)** | Total model text generation throughput time. | `1.2 seconds` | **LangSmith UI** / **Prometheus** |
| | **Input / Output Token Count** | Raw number of prompt and completion tokens processed. | `prompt: 840, completion: 120` | **LangSmith UI** / **Prometheus** |
| | **Faithfulness (Groundedness)** | Metric checking if the response is fully backed by context. | `score = 0.95` | **LangSmith UI** / **SQLite** (`audit_trail`) |
| | **Answer Relevancy** | Metric checking if the response matches the query intent. | `score = 0.91` | **LangSmith UI** / **Ragas Reports** |
| | User Satisfaction Rating | Human feedback clicks (👍 / 👎) and qualitative reviews. | `1 (Thumbs Up), "Good info"` | **SQLite** (`feedback_loop` table) |

---

## 🔍 5. Concrete Telemetry Examples

### A. Prometheus Token & Latency Metrics Stream (`/metrics` endpoint)
```text
# HELP askgovragbot_token_usage_total Total LLM tokens consumed.
# TYPE askgovragbot_token_usage_total counter
askgovragbot_token_usage_total{role="Manager",type="prompt"} 8420.0
askgovragbot_token_usage_total{role="Manager",type="completion"} 1450.0

# HELP askgovragbot_llm_ttft_seconds Latency to first streaming token.
# TYPE askgovragbot_llm_ttft_seconds summary
askgovragbot_llm_ttft_seconds{quantile="0.5"} 0.35
askgovragbot_llm_ttft_seconds{quantile="0.9"} 0.52
```

### B. LangSmith Execution Trace Node JSON (with Token & Latency Details)
```json
{
  "name": "qa_synthesis_node",
  "run_type": "llm",
  "start_time": "2026-06-10T00:11:38.298Z",
  "end_time": "2026-06-10T00:11:39.420Z",
  "inputs": {
    "prompts": ["System: You are an expert... Question: What is the budget cap for manager raises?"]
  },
  "outputs": {
    "generations": [
      {
        "text": "The budget cap for discretionary raises is 8% annually. [Source: hr_policy.xml]"
      }
    ]
  },
  "response_metadata": {
    "token_usage": {
      "prompt_tokens": 840,
      "completion_tokens": 42,
      "total_tokens": 882
    },
    "model_name": "command-r-08-2024",
    "time_to_first_token": 0.380
  }
}
```

### C. SQLite Ledger Database Audit Record
Stored locally in `data/askgovragbot_governance_ledger.db` under the `audit_trail` table:
```sql
SELECT session_id, user_role, raw_query, response, is_grounded, groundedness_score 
FROM audit_trail 
LIMIT 1;
```
| session_id | user_role | raw_query | response | is_grounded | groundedness_score |
| :--- | :--- | :--- | :--- | :---: | :--- |
| `demo-session-1` | `Manager` | What is the budget cap for raises? | The budget cap for raises is 8%... | `1` (True) | `0.95` |

---

## 🛠️ 6. Instrumentation Readiness Checklist

Here is a checklist of which telemetry metrics are functional out of the box versus which require application code updates:

### 🟢 A. Works Out of the Box (No Code Changes Needed)
* **LangSmith Observability UI (TTFT, TTLT, and Token Counts)**: By setting `LANGCHAIN_TRACING_V2=true` in `.env`, the LangChain SDK automatically hooks the underlying LLM client execution loop and transmits detailed prompt/completion tokens and latency measurements.
* **Offline Evaluations (Faithfulness & Relevancy)**: The batch evaluator runner ([scripts/evaluate.py](scripts/evaluate.py)) is already written and pre-configured to compute Ragas metrics across test questions.
* **Online Groundedness Scores**: The real-time LLM-as-a-judge check is already compiled into the LangGraph state machine ([app/graph.py](app/graph.py)), checking and saving groundedness outputs into the SQLite database.

### 🟡 B. Custom Code Required (Optional Integrations)
* **Prometheus Token Costs & TTFT Histograms**: Our active Prometheus client in [app/main.py](app/main.py) is instrumented for end-to-end API duration, request counts, PII masks, and hallucinations. If you want **Prometheus** (rather than LangSmith) to chart raw prompt tokens or streaming token latency histograms, you must add Prometheus `Counter` / `Histogram` objects inside `app/main.py` and increment them within the endpoint response handler logic.
