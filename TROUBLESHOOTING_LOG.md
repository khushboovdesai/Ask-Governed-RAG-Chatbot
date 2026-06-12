# AskGovRAGBot - Troubleshooting & Dependency Resolution Log

This document records the technical hurdles encountered during environment setup, dependency resolution blocks, and the architectural solutions implemented to build a production-ready RAG application.

---

## Issue 1: NumPy compilation failure on Python 3.14

### Problem Description
When running `./venv/bin/pip install -r requirements.txt`, pip crashed while trying to build `numpy-1.26.4` from source, raising compile errors:
`ERROR: Unknown compiler(s): [['cc'], ['gcc'], ['clang'], ['nvc'], ['pgcc'], ['icc'], ['icx']]`
`error: metadata-generation-failed`

### Root Cause
1. **Python 3.14 Pre-release**: Your Mac is running the pre-release version **Python 3.14**. Because this version is highly experimental, binary packages (wheels) are not yet published for older libraries.
2. **ChromaDB Dependency limits**: LangChain's Chroma wrapper (`langchain-chroma`) requires `numpy < 2.0.0`. 
3. **Source Compilation Failure**: Since precompiled wheels for `numpy < 2.0.0` do not support Python 3.14, pip was forced to download the source distribution and compile it locally. The compilation failed because the system compiler flags or libraries required for building older NumPy versions are not set up inside the active workspace environment PATH.

---

## Resolution Strategy: Native Client Wrappers & Pure Python DBs

To bypass this dependency conflict, we refactored the database integration:

### 1. Removing langchain-chroma
We removed `langchain-chroma` from `requirements.txt`. This lifted the strict `numpy < 2.0.0` dependency limit, allowing pip to download the newer **NumPy 2.x** binary wheel, which compiles and installs natively on Python 3.14.

### 2. Swapping compiled wrappers for Pure Python DB Clients
Instead of using binary-heavy LangChain database wrappers, we switched to **`qdrant-client`** and **`pinecone-client`**. 
* **Why**: These libraries are written in pure Python. They install instantly on Python 3.14 without any local compilation.
* **Qdrant** provides a local file-based vector engine (like SQLite) that runs completely locally without requiring cloud keys or API tokens.
* **Pinecone** provides our managed cloud vector database for production.

### 3. Custom VectorDatabaseStore Interface (SOLID Factory)
To keep the core RAG code and LangGraph nodes unchanged, we implemented a custom factory interface inside `app/factory.py`:
* We defined a standard abstract class `VectorDatabaseStore` containing:
  * `add_documents()`
  * `similarity_search(query, k, permission_level)`
* We implemented `QdrantVectorStore` and `PineconeVectorStore` using the native client libraries (`qdrant_client` and `pinecone`) directly inside our codebase.
* This encapsulates all database calls, so the rest of the application remains clean and uses standardized vector lookup contracts.

---

## Issue 2: LangChain Wrapper Packages Incompatible with Python >= 3.14

### Problem Description
Even when removing the `numpy` constraint, pip blocked the installation of LangChain integration libraries like `langchain-qdrant` and `langchain-pinecone` with the error:
`ERROR: Ignored the following versions that require a different python version: ... Requires-Python >=3.9, <3.14`

### Root Cause
Most official LangChain database connector wrappers explicitly check the Python environment on install. They restrict compatibility to `Python < 3.14` because Python 3.14 is a pre-release and has not been tested. Consequently, pip ignores all compatible versions, throwing:
`ERROR: No matching distribution found`

### Ultimate Resolution: Isolating the Environment to Python 3.12
To enable standard LangChain developer APIs (such as `Chroma`, `Qdrant`, and `PineconeVectorStore`) without writing custom database wrappers:
1. **Isolated Binary Install**: We install **Python 3.12** locally using Homebrew (`brew install python@3.12`). This registers `python3.12` as an available compiler, without altering your default macOS Python 3.14 environment.
2. **Recreating the Virtual Environment**: We delete the Python 3.14 virtual environment and recreate a clean one bound to the stable release:
   `python3.12 -m venv venv`
3. **Restoring Standard requirements.txt**: We restore the standard `langchain-chroma`, `langchain-qdrant`, and `langchain-pinecone` packages in `requirements.txt`.
4. **Standard Developer Experience**: This allows developers to use direct LangChain vector database APIs natively, keeping code identical to production guidelines.

---

## Issue 3: `pip install -r requirements.txt` hangs inside the existing venv

### Problem Description
`pip install -r requirements.txt` can appear to hang before package installation starts. In one observed case, interrupting the command showed that `venv/bin/pip` was still importing pip's own CLI modules, such as `pip._internal.cli.autocompletion` and `pip._internal.cli.main_parser`.

If even this command hangs, the virtual environment itself is likely wedged:

```bash
python -m pip --version
```

### Root Cause
This points to a corrupted or unhealthy local virtual environment rather than a specific package in `requirements.txt`. Continuing to install into the same `venv` is unreliable because pip may not even finish starting.

### Resolution: Rebuild the venv
Rebuilding `venv` does not affect Git-tracked files, staged changes, or project source code. It only replaces the local dependency environment.

From the repository root:

```bash
deactivate 2>/dev/null || true
mv venv venv_broken
python3.12 -m venv venv
source venv/bin/activate
python -m pip --version
python -m pip install --upgrade pip setuptools wheel
python -m pip install -r requirements.txt
```

If `python3.12` is not available:

```bash
python3 -m venv venv
```

Always prefer `python -m pip` over plain `pip` so installs target the active virtual environment.

---

*Note: For the detailed database schema and orchestrator tracing flows, see [DESIGN_DISCUSSION.md](DESIGN_DISCUSSION.md).*
