import sqlite3
import json
from datetime import datetime
from typing import Optional, List, Dict
from app.config import settings

def get_db_connection():
    conn = sqlite3.connect(settings.DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Initializes RDBMS tables for audit logs, user feedback, and API cache."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Audit Trail table (persistent logs)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS audit_trail (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            run_id TEXT,
            raw_query TEXT NOT NULL,
            masked_query TEXT NOT NULL,
            response TEXT NOT NULL,
            user_role TEXT NOT NULL,
            retrieved_docs TEXT,  -- JSON string of docs
            nodes_visited TEXT,   -- JSON string of nodes path
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # User Feedback table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS feedback_loop (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            run_id TEXT,
            rating INTEGER NOT NULL, -- 1 for up, 0 for down
            comment TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Embedding Cache table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS embedding_cache (
            query_text TEXT PRIMARY KEY,
            embedding_vector TEXT NOT NULL, -- JSON serialized list of floats
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # LLM Cache table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS llm_cache (
            prompt_hash TEXT PRIMARY KEY,
            response_text TEXT NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    conn.commit()
    conn.close()

def log_interaction(session_id: str, run_id: str, raw_query: str, masked_query: str, 
                    response: str, user_role: str, retrieved_docs: List[dict], 
                    nodes_visited: List[str]):
    """Logs a single query transaction in the audit trail database."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO audit_trail 
        (session_id, run_id, raw_query, masked_query, response, user_role, retrieved_docs, nodes_visited)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        session_id,
        run_id,
        raw_query,
        masked_query,
        response,
        user_role,
        json.dumps(retrieved_docs),
        json.dumps(nodes_visited)
    ))
    conn.commit()
    conn.close()

def log_feedback(session_id: str, run_id: str, rating: int, comment: Optional[str] = None):
    """Saves user rating and comments into the feedback database table."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO feedback_loop (session_id, run_id, rating, comment)
        VALUES (?, ?, ?, ?)
    """, (session_id, run_id, rating, comment))
    conn.commit()
    conn.close()

def get_cached_embedding(query_text: str) -> Optional[List[float]]:
    """Retrieves cached vector representation if available."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT embedding_vector FROM embedding_cache WHERE query_text = ?", (query_text,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return json.loads(row["embedding_vector"])
    return None

def set_cached_embedding(query_text: str, embedding_vector: List[float]):
    """Caches query vector embeddings to save API costs."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT OR REPLACE INTO embedding_cache (query_text, embedding_vector) VALUES (?, ?)", 
                       (query_text, json.dumps(embedding_vector)))
        conn.commit()
    except Exception as e:
        print(f"[ERROR] Database cache write failed: {e}")
    finally:
        conn.close()

def get_cached_llm(prompt_hash: str) -> Optional[str]:
    """Retrieves cached response matching prompt signature."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT response_text FROM llm_cache WHERE prompt_hash = ?", (prompt_hash,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return row["response_text"]
    return None

def set_cached_llm(prompt_hash: str, response_text: str):
    """Caches LLM generation output."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT OR REPLACE INTO llm_cache (prompt_hash, response_text) VALUES (?, ?)", 
                       (prompt_hash, response_text))
        conn.commit()
    except Exception as e:
        print(f"[ERROR] Database LLM cache write failed: {e}")
    finally:
        conn.close()
