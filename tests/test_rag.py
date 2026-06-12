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
from langchain_core.documents import Document

# Ensure project root is in python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import settings
from app.security import pii_manager
from app.database import init_db, log_feedback, log_interaction, get_db_connection
from app.graph import (
    MODEL_UNAVAILABLE_RESPONSE,
    classify_intent_deterministically,
    compiled_graph,
    general_chat_node,
    summarize_model_error,
    route_intent_conditional,
    extract_direct_supported_answer,
    is_direct_answer_supported,
)

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

def test_deterministic_intent_routes_pii_benefits_question_to_policy():
    """
    Ensures PII-heavy HR/benefits requests still route to policy retrieval when
    the LLM router is unavailable or rate limited.
    """
    masked_text, _ = pii_manager.mask_pii(
        "Help me contact HR manager John Doe at john.doe@auratech.com about benefits via employee role"
    )

    assert classify_intent_deterministically(masked_text) == "policy_qa"

def test_model_failure_returns_safe_availability_message(monkeypatch):
    """
    Ensures provider 503/rate-limit errors are not exposed directly to users.
    """
    class FailingChatModel:
        def invoke(self, messages):
            raise RuntimeError("503 UNAVAILABLE: high demand")

    monkeypatch.setattr("app.graph.get_chat_model", lambda: FailingChatModel())

    result = general_chat_node({
        "masked_query": "Hello",
        "nodes_visited": [],
    })

    assert result["generated_answer"] == MODEL_UNAVAILABLE_RESPONSE
    assert "503" not in result["generated_answer"]

def test_model_error_summary_redacts_provider_payload():
    """
    Ensures server logs summarize provider failures without dumping raw quota JSON.
    """
    raw_error = RuntimeError(
        "Error calling model 'gemini-2.5-flash' (RESOURCE_EXHAUSTED): "
        "429 RESOURCE_EXHAUSTED. {'error': {'message': 'quota exceeded', "
        "'url': 'https://ai.google.dev/gemini-api/docs/rate-limits'}}"
    )

    summary = summarize_model_error(raw_error)

    assert summary == "Gemini quota/rate limit reached"
    assert "https://" not in summary
    assert "gemini-2.5-flash" not in summary

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

def test_manager_raise_cap_direct_answer_from_authorized_context():
    """
    Verifies that manager raise-cap wording is answered from the retrieved HR-303
    salary-adjustment chunk instead of falling through to source coverage refusal.
    """
    docs = [
        Document(
            page_content=(
                "Company: AuraTech\n"
                "Department: Human Resources\n"
                "Policy: Performance Management and Compensation Adjustments (ID: HR-303)\n"
                "Section: Salary Adjustments and Promotion Triggers\n"
                "Content: Discretionary salary increases are capped at 8% annually."
            ),
            metadata={
                "policy_id": "HR-303",
                "section_title": "Salary Adjustments and Promotion Triggers",
                "source": "hr_policy.xml",
                "min_permission_level": 3,
            },
        )
    ]

    answer = extract_direct_supported_answer(
        "What is the budget limit for manager salary raises?",
        docs,
    )

    assert answer is not None
    assert "8% annually" in answer
    assert "HR-303" in answer
    assert is_direct_answer_supported(answer, docs)

def test_pii_benefits_contact_direct_answer_from_authorized_context():
    """
    Verifies that PII-heavy benefits/contact wording is answered from the
    authorized HR-202 contact chunk instead of falling through to source coverage.
    """
    docs = [
        Document(
            page_content=(
                "Company: AuraTech\n"
                "Department: Human Resources\n"
                "Policy: Hybrid Work and PTO Allowance (ID: HR-202)\n"
                "Section: Emergency Contact\n"
                "Content: For critical HR emergencies or leave queries, contact the HR "
                "Benefits Specialist, Sarah Jenkins, at sarah.jenkins@auratech.com or "
                "call her desk phone at 555-014-9922."
            ),
            metadata={
                "policy_id": "HR-202",
                "section_title": "Emergency Contact",
                "source": "hr_policy.xml",
                "min_permission_level": 2,
            },
        )
    ]

    masked_text, _ = pii_manager.mask_pii(
        "Help me contact HR manager John Doe at john.doe@auratech.com about benefits via employee role"
    )
    answer = extract_direct_supported_answer(masked_text, docs)

    assert answer is not None
    assert "HR-202" in answer
    assert "Sarah Jenkins" in answer
    assert "sarah.jenkins@auratech.com" in answer
    assert is_direct_answer_supported(answer, docs)
