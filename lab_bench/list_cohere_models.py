import os
from dotenv import load_dotenv
import cohere

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(PROJECT_ROOT, ".env"))
api_key = os.environ.get("COHERE_API_KEY")

try:
    co = cohere.Client(api_key)
    models = co.models.list()
    print("Available Cohere Models:")
    for m in models.models:
        if "chat" in m.endpoints:
            print(f"- {m.name} (endpoints: {m.endpoints})")
except Exception as e:
    print(f"Error: {e}")
