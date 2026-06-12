import os
import sys
from dotenv import load_dotenv

# Ensure project root is in python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

load_dotenv()

from app.graph import compiled_graph

def run_query(query: str, role: str, session_id: str):
    print(f"\n--- Running query as '{role}': '{query}' ---")
    config = {"configurable": {"thread_id": session_id}}
    state_result = compiled_graph.invoke({
        "query": query,
        "user_role": role,
        "nodes_visited": []
    }, config=config)
    
    print(f"Matched Intent: {state_result.get('intent')}")
    print(f"Nodes Visited: {state_result.get('nodes_visited')}")
    print(f"Final Answer: {state_result.get('final_answer')}")
    
    docs = state_result.get("retrieved_docs", [])
    print(f"Retrieved Documents Count: {len(docs)}")
    for i, d in enumerate(docs):
        print(f"  Doc {i+1} Metadata: {d.metadata}")
        print(f"  Doc {i+1} Snippet: {d.page_content[:150]}...")

# Scenario 1: Contractor trying to query Manager policies (should refuse access)
run_query(
    query="What is the budget limit for manager salary raises?",
    role="Contractor",
    session_id="test-session-1"
)

# Scenario 2: Manager querying Manager policies (should successfully retrieve and answer)
run_query(
    query="What is the budget limit for manager salary raises?",
    role="Manager",
    session_id="test-session-2"
)

# Scenario 3: Employee querying with PII (should mask in-flight, generate response, and de-mask on return)
run_query(
    query="Help me contact HR manager John Doe at john.doe@auratech.com about benefits.",
    role="Employee",
    session_id="test-session-3"
)
