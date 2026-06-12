import os
from dotenv import load_dotenv
from langchain_cohere import CohereEmbeddings

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(PROJECT_ROOT, ".env"))
api_key = os.environ.get("COHERE_API_KEY")
print(f"Loaded COHERE_API_KEY: {api_key[:8]}...{api_key[-8:] if api_key else ''}")

try:
    embeddings = CohereEmbeddings(cohere_api_key=api_key, model="embed-english-v3.0")
    vec = embeddings.embed_query("Hello world")
    print(f"Embedded successfully. Vector length: {len(vec)}")
except Exception as e:
    print(f"Error embedding: {e}")
