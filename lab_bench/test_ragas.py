import os
import sys
import types

# Programmatically mock the missing langchain_community.chat_models.vertexai module
# to satisfy Ragas' unconditional startup import without installing Vertex AI.
try:
    import langchain_community.chat_models.vertexai
except ModuleNotFoundError:
    # Mock chat_models
    try:
        import langchain_community.chat_models
    except ModuleNotFoundError:
        langchain_community.chat_models = types.ModuleType("chat_models")
        sys.modules["langchain_community.chat_models"] = langchain_community.chat_models
        
    mock_vertexai = types.ModuleType("vertexai")
    mock_vertexai.ChatVertexAI = type("ChatVertexAI", (object,), {}) # Dummy class
    sys.modules["langchain_community.chat_models.vertexai"] = mock_vertexai
    print("[INFO] Mocked langchain_community.chat_models.vertexai successfully.")

from dotenv import load_dotenv
from datasets import Dataset
from ragas import evaluate
from ragas.metrics import faithfulness, answer_relevancy
from langchain_cohere import ChatCohere, CohereEmbeddings
from ragas.llms import LangchainLLMWrapper

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(PROJECT_ROOT, ".env"))
cohere_api_key = os.environ.get("COHERE_API_KEY")

print("Initializing Cohere models for Ragas...")
cohere_llm = ChatCohere(cohere_api_key=cohere_api_key, model="command-r-08-2024", max_tokens=2048)

# Wrap Cohere model in LangchainLLMWrapper with is_finished_parser returning True
evaluator_llm = LangchainLLMWrapper(
    langchain_llm=cohere_llm,
    is_finished_parser=lambda response: True
)
evaluator_embeddings = CohereEmbeddings(cohere_api_key=cohere_api_key, model="embed-english-v3.0")

# Sample evaluation data matching Ragas expected schema
data = {
    "question": ["What is the hybrid office attendance requirement?"],
    "contexts": [["According to the Hybrid Work Policy (HR-202), standard employees work in-office at least 2 days per week."]],
    "answer": ["Standard employees work in-office at least 2 days per week."]
}

dataset = Dataset.from_dict(data)

print("Running Ragas evaluation...")
try:
    result = evaluate(
        dataset=dataset,
        metrics=[faithfulness, answer_relevancy],
        llm=evaluator_llm,
        embeddings=evaluator_embeddings
    )
    print("Ragas evaluation completed successfully!")
    print(result)
except Exception as e:
    print(f"Ragas evaluation failed: {e}")
