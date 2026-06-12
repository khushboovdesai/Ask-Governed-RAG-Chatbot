import os
from typing import Any, List, Optional, Dict
from langchain_core.embeddings import Embeddings
from langchain_core.vectorstores import VectorStore
from app.config import settings

# =============================================================================
# FALLBACK OFFLINE EMBEDDINGS (To run without external API keys or local models)
# =============================================================================
class LocalPseudoEmbeddings(Embeddings):
    """Generates deterministic pseudo-embeddings locally without API calls or downloads."""
    
    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        return [self.embed_query(txt) for txt in texts]

    def embed_query(self, text: str) -> List[float]:
        vector = []
        for i in range(1024):
            val = abs(hash(text + str(i))) % 1000 / 1000.0
            vector.append(val)
        return vector

class RateLimitedEmbeddings(Embeddings):
    """Wraps an Embeddings model to enforce a delay between calls, preventing free-tier rate limit crashes."""
    
    def __init__(self, inner: Embeddings, requests_per_minute: int = 9):
        self.inner = inner
        self.min_interval = 60.0 / requests_per_minute
        import time
        self.time = time
        self.last_call = 0.0

    def _throttle(self):
        now = self.time.time()
        elapsed = now - self.last_call
        if elapsed < self.min_interval:
            self.time.sleep(self.min_interval - elapsed)
        self.last_call = self.time.time()

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        self._throttle()
        return self.inner.embed_documents(texts)

    def embed_query(self, text: str) -> List[float]:
        self._throttle()
        return self.inner.embed_query(text)

def get_embeddings() -> Embeddings:
    """Instantiates and returns the configured Embeddings encoder."""
    provider = settings.EMBEDDING_PROVIDER
    
    def is_valid_key(key: str) -> bool:
        return bool(key and not key.startswith("your_") and key.strip() != "")
    
    if provider == "local":
        try:
            from langchain_community.embeddings import HuggingFaceBgeEmbeddings
            return HuggingFaceBgeEmbeddings(
                model_name="BAAI/bge-large-en-v1.5",
                model_kwargs={'device': 'cpu'},
                encode_kwargs={'normalize_embeddings': True}
            )
        except Exception as e:
            print(f"[INFO] Failed loading HuggingFaceBgeEmbeddings ({e}). Using LocalPseudoEmbeddings.")
            return LocalPseudoEmbeddings()
            
    elif provider == "cohere":
        if not is_valid_key(settings.COHERE_API_KEY):
            print("[INFO] Valid COHERE_API_KEY not configured. Using LocalPseudoEmbeddings.")
            return LocalPseudoEmbeddings()
        from langchain_cohere import CohereEmbeddings
        cohere_model = CohereEmbeddings(
            model="embed-english-v3.0",
            cohere_api_key=settings.COHERE_API_KEY
        )
        # Free Cohere keys have a strict limit of 10 requests per minute.
        # We wrap it to throttle requests to 9 per minute to remain safe.
        return RateLimitedEmbeddings(cohere_model, requests_per_minute=9)
        
    elif provider == "openai":
        if not is_valid_key(settings.OPENAI_API_KEY):
            print("[INFO] Valid OPENAI_API_KEY not configured. Using LocalPseudoEmbeddings.")
            return LocalPseudoEmbeddings()
        from langchain_openai import OpenAIEmbeddings
        return OpenAIEmbeddings(
            model="text-embedding-3-large",
            openai_api_key=settings.OPENAI_API_KEY
        )

    return LocalPseudoEmbeddings()

def get_vector_store() -> VectorStore:
    """Instantiates and returns the configured standard LangChain VectorStore client."""
    embeddings = get_embeddings()
    db_type = settings.VECTOR_STORE
    
    def is_valid_key(key: str) -> bool:
        return bool(key and not key.startswith("your_") and key.strip() != "")
    
    if db_type == "pinecone" and is_valid_key(settings.PINECONE_API_KEY):
        try:
            from langchain_pinecone import PineconeVectorStore
            # Initialize Pinecone store
            return PineconeVectorStore(
                index_name=settings.PINECONE_INDEX_NAME,
                embedding=embeddings,
                pinecone_api_key=settings.PINECONE_API_KEY
            )
        except Exception as e:
            print(f"[WARNING] Pinecone initialization failed ({e}). Falling back to local Qdrant.")
            db_type = "qdrant"
            
    if db_type == "qdrant":
        try:
            from langchain_qdrant import QdrantVectorStore
            from qdrant_client import QdrantClient
            from qdrant_client.models import Distance, VectorParams
            
            qdrant_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "qdrant_db")
            os.makedirs(qdrant_path, exist_ok=True)
            
            client = QdrantClient(path=qdrant_path)
            collection_name = "askgovragbot-collection"
            
            # Determine vector size (BGE and Cohere use 1024d, pseudo-embeddings use 1024d, OpenAI uses 3072d for text-embedding-3-large)
            vector_size = 1024
            if settings.EMBEDDING_PROVIDER == "openai":
                vector_size = 3072
                
            if not client.collection_exists(collection_name):
                client.create_collection(
                    collection_name=collection_name,
                    vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE)
                )
                
            return QdrantVectorStore(
                client=client,
                collection_name=collection_name,
                embedding=embeddings
            )
        except Exception as e:
            print(f"[WARNING] Qdrant initialization failed ({e}). Falling back to local Chroma.")
            db_type = "chroma"

    # Default to Chroma
    from langchain_chroma import Chroma
    chroma_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "chroma_db")
    os.makedirs(chroma_path, exist_ok=True)
    
    return Chroma(
        persist_directory=chroma_path,
        embedding_function=embeddings,
        collection_name="askgovragbot-collection"
    )
