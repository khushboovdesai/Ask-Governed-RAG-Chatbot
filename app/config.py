import os
from dotenv import load_dotenv

# Load .env file if it exists
load_dotenv()

class Settings:
    # Server configuration
    PORT: int = int(os.getenv("PORT", "8000"))
    HOST: str = os.getenv("HOST", "0.0.0.0")

    # DB & Model configurations
    VECTOR_STORE: str = os.getenv("VECTOR_STORE", "chroma").lower()  # "chroma" or "pinecone"
    LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "gemini").lower()  # "gemini" or "openai" or "nebius"
    LLM_MODEL: str = os.getenv("LLM_MODEL", "gemini-2.5-flash")
    EMBEDDING_PROVIDER: str = os.getenv("EMBEDDING_PROVIDER", "cohere").lower()  # "local" or "cohere" or "openai"

    # API Keys
    GOOGLE_API_KEY: str = os.getenv("GOOGLE_API_KEY", "")
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    COHERE_API_KEY: str = os.getenv("COHERE_API_KEY", "")
    PINECONE_API_KEY: str = os.getenv("PINECONE_API_KEY", "")
    PINECONE_INDEX_NAME: str = os.getenv("PINECONE_INDEX_NAME", "askgovragbot-index")

    # LangSmith Tracing
    LANGCHAIN_TRACING_V2: bool = os.getenv("LANGCHAIN_TRACING_V2", "false").lower() == "true"
    LANGCHAIN_ENDPOINT: str = os.getenv("LANGCHAIN_ENDPOINT", "https://api.smith.langchain.com")
    LANGCHAIN_API_KEY: str = os.getenv("LANGCHAIN_API_KEY") or os.getenv("LANGSMITH_API_KEY") or ""
    LANGCHAIN_PROJECT: str = os.getenv("LANGCHAIN_PROJECT", "AskGovRAGBot")

    # SQLite Paths
    DB_PATH: str = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "askgovragbot_governance_ledger.db")
    CACHE_PATH: str = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "app_cache")

    def validate(self):
        """Validates that necessary API keys are present based on provider choices."""
        if self.LANGCHAIN_API_KEY:
            os.environ["LANGCHAIN_API_KEY"] = self.LANGCHAIN_API_KEY
        if self.LLM_PROVIDER == "gemini" and not self.GOOGLE_API_KEY:
            print("[WARNING] GOOGLE_API_KEY is not configured, Gemini calls will fail.")
        if self.LLM_PROVIDER == "openai" and not self.OPENAI_API_KEY:
            print("[WARNING] OPENAI_API_KEY is not configured, OpenAI calls will fail.")
        if self.LLM_PROVIDER == "cohere" and not self.COHERE_API_KEY:
            print("[WARNING] COHERE_API_KEY is not configured, Cohere calls will fail.")
        if self.VECTOR_STORE == "pinecone" and (not self.PINECONE_API_KEY or not self.PINECONE_INDEX_NAME):
            print("[WARNING] Pinecone configurations are missing. Defaulting database to local Chroma.")
            os.environ["VECTOR_STORE"] = "chroma"
            self.VECTOR_STORE = "chroma"

settings = Settings()
settings.validate()
