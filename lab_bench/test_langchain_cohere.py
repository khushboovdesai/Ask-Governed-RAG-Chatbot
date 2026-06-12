import os
from dotenv import load_dotenv
from langchain_cohere import ChatCohere

# Load project .env
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(PROJECT_ROOT, ".env"))
api_key = os.environ.get("COHERE_API_KEY")
print(f"Loaded COHERE_API_KEY: {api_key[:8]}...{api_key[-8:] if api_key else ''}")

try:
    llm = ChatCohere(cohere_api_key=api_key)
    res = llm.invoke("Hello, how are you?")
    print(f"Response: {res.content}")
except Exception as e:
    print(f"Error invoking: {e}")
