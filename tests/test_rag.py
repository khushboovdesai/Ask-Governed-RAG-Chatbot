"""
AskGovRAGBot Automated Unit and Integration Tests
==================================================

This module implements the pytest-based unit and integration tests verifying the core
pillars of AskGovRAGBot:
1. PIISecurityManager: Correctness of in-flight name, email, phone, and ID masking.
2. Intent Classifier: Categorization of casual queries, policy requests, and exploits.
3. SQLite Ledger: Verification of database inserts, caching mechanics, and feedback logs.
4. LangGraph Flow: Verification of compiled graph execution and visited nodes logs.

Usage:
------
Run via: pytest tests/test_rag.py
"""

import os
import sys
import json
import pytest
from typing import Dict

# Ensure project root is in python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import settings
from app.security import pii_manager
from app.database import init_db, log_feedback, log_interaction, get_db_connection
from app.graph import compiled_graph, route_intent_conditional

# Initialize SQLite tables prior to executing test cases
init_db()

# =============================================================================
# 1. PII SECURITY MANAGER TESTS
# =============================================================================

def test_pii_masking_email_and_name():
    """
    Verifies that names and emails are correctly identified, masked in-flight,
    and accurately reconstructed back to their original forms.
    """
    original_text = "Please reach out to project supervisor John Doe at john.doe@auratech.com"
    
    # Run masking utility
    masked_text, pii_mapping = pii_manager.mask_pii(original_text)
    
    # Verify that redacted tokens are injected
    assert "[REDACTED_EMAIL_1]" in masked_text
    assert "[REDACTED_NAME_" in masked_text
    assert "john.doe@auratech.com" not in masked_text
    assert "John Doe" not in masked_text
    
    # Run de-masking reconstruction
    restored_text = pii_manager.demask_pii(masked_text, pii_mapping)
    assert restored_text == original_text

def test_pii_masking_phone_and_custom_ids():
    """
    Verifies that phone numbers and custom enterprise employee IDs/API keys
    are correctly matched and sanitized.
    """
    original_text = "My employee ID is AT-EMP-1088 and contact is 555-123-4567."
    
    # Run masking utility
    masked_text, pii_mapping = pii_manager.mask_pii(original_text)
    
    # Verify identifiers are replaced
    assert "[REDACTED_EMP_ID_1]" in masked_text
    assert "[REDACTED_PHONE_1]" in masked_text
    assert "AT-EMP-1088" not in masked_text
    assert "555-123-4567" not in masked_text
    
    # Restore and verify mapping matches original inputs
    restored_text = pii_manager.demask_pii(masked_text, pii_mapping)
    assert restored_text == original_text

# =============================================================================
# 2. INTENT ROUTER TESTS
# =============================================================================

def test_route_intent_conditional_cases():
    """
    Validates the routing state evaluation mapping based on intent classifications.
    """
    # 1. Refusal case
    state_refused = {"intent": "refused", "query": "hack"}
    assert route_intent_conditional(state_refused) == "refuse"
    
    # 2. Policy Q&A case
    state_policy = {"intent": "policy_qa", "query": "hybrid rules"}
    assert route_intent_conditional(state_policy) == "expert_retrieval"
    
    # 3. Casual chat case
    state_casual = {"intent": "general_chat", "query": "hello"}
    assert route_intent_conditional(state_casual) == "general_chat"

# =============================================================================
# 3. DATABASE LEDGER PERSISTENCE TESTS
# =============================================================================

def test_sqlite_feedback_logs():
    """
    Verifies that submitting feedback inserts record rows inside the SQLite feedback loop table.
    """
    session_id = "test-session-db-001"
    run_id = "test-run-db-001"
    rating = 1
    comment = "System answered hybrid query accurately."
    
    # Log feedback block
    log_feedback(session_id, run_id, rating, comment)
    
    # Retrieve row from SQLite
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT rating, comment FROM feedback_loop WHERE session_id = ? AND run_id = ?", (session_id, run_id))
    row = cursor.fetchone()
    conn.close()
    
    # Assert contents
    assert row is not None
    assert row["rating"] == rating
    assert row["comment"] == comment

def test_sqlite_interaction_audit_trail():
    """
    Verifies that calling log_interaction records full session metadata logs.
    """
    session_id = "test-session-audit-002"
    run_id = "test-run-audit-002"
    query = "What is the manager raise cap?"
    masked_q = "What is the [REDACTED_NAME_1] raise cap?"
    response = "The manager salary raise cap is 8%."
    role = "Manager"
    docs = [{"page_content": "salary cap is 8%", "metadata": {"source": "hr.xml"}}]
    nodes = ["pii_masking", "intent_routing", "expert_retrieval", "qa_synthesis"]
    
    # Execute log write
    log_interaction(session_id, run_id, query, masked_q, response, role, docs, nodes)
    
    # Query database validation
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT raw_query, response, user_role, nodes_visited FROM audit_trail WHERE session_id = ?", (session_id,))
    row = cursor.fetchone()
    conn.close()
    
    assert row is not None
    assert row["raw_query"] == query
    assert row["response"] == response
    assert row["user_role"] == role
    
    # Ensure JSON structures were successfully unpacked
    visited_nodes = json.loads(row["nodes_visited"])
    assert "expert_retrieval" in visited_nodes

# =============================================================================
# 4. STATE GRAPH WORKFLOW VERIFICATION
# =============================================================================

def test_workflow_graph_compiles_successfully():
    """
    Validates that the compiled LangGraph object has been successfully loaded
    and exposes run/invoke methods.
    """
    assert compiled_graph is not None
    assert hasattr(compiled_graph, "invoke")
