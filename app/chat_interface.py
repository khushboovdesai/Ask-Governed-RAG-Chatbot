import os
from typing import Any, List, Optional
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.messages import AIMessage
from app.config import settings

ACCESS_OR_COVERAGE_REFUSAL = (
    "Access/Source Coverage Guardrail: I cannot verify this policy for your current role "
    "from the authorized knowledge base. The requested information may be unavailable, "
    "outside the indexed policy documents, or restricted by RBAC policy. Please consult HR "
    "or the policy owner."
)

SOURCE_COVERAGE_REFUSAL = (
    "Source Coverage Guardrail: I cannot verify this policy in the retrieved authorized "
    "context. It may be outside the indexed knowledge base or restricted by RBAC policy. "
    "Please consult HR or the policy owner."
)

class FallbackOfflineChatModel(BaseChatModel):
    """Generates mock responses for development when API keys are absent."""
    
    def _generate(
        self,
        messages: List[Any],
        stop: Optional[List[str]] = None,
        run_manager: Optional[Any] = None,
        **kwargs: Any
    ) -> ChatResult:
        # Find system and human messages
        system_content = ""
        human_content = ""
        for msg in messages:
            if msg.__class__.__name__ == "SystemMessage" or getattr(msg, "type", "") == "system":
                system_content = msg.content
            elif msg.__class__.__name__ == "HumanMessage" or getattr(msg, "type", "") == "human":
                human_content = msg.content
                
        last_message = human_content if human_content else (messages[-1].content if messages else "")
        response_text = "This is a mock response from AskGovRAGBot. [MOCK_ANSWER]"
        
        # Check if this is a RAG synthesis call by looking at system prompt
        is_rag_call = "Retrieved Policy Context:" in system_content
        context_contains_hr101 = "HR-101" in system_content
        context_contains_hr202 = "HR-202" in system_content
        context_contains_hr303 = "HR-303" in system_content
        context_contains_it = "IT-101" in system_content or "password" in system_content.lower()
        context_contains_dev = "DEV-101" in system_content or "code review" in system_content.lower()
        
        low_msg = last_message.lower()
        
        if is_rag_call:
            # RAG flow: only answer if the relevant document is present in the context!
            if "conduct" in low_msg or "workforce" in low_msg:
                if context_contains_hr101:
                    response_text = "According to the General Code of Conduct (HR-101), all workforce members must perform duties ethically. Contact support@auratech.com."
                else:
                    response_text = ACCESS_OR_COVERAGE_REFUSAL
            elif "hybrid" in low_msg or "pto" in low_msg:
                if context_contains_hr202:
                    response_text = "According to the Hybrid Work and PTO Allowance Policy (HR-202), standard employees work in-office at least 2 days per week and receive a $500 stipend."
                else:
                    response_text = ACCESS_OR_COVERAGE_REFUSAL
            elif "budget" in low_msg or "compensation" in low_msg or "salary" in low_msg or "raise" in low_msg:
                if context_contains_hr303:
                    response_text = "According to the Performance policy (HR-303), manager salary increases are capped at 8% annually. Marcus Sterling approves promotion triggers."
                else:
                    response_text = ACCESS_OR_COVERAGE_REFUSAL
            elif "password" in low_msg or "security" in low_msg:
                if context_contains_it:
                    response_text = "According to the Device Passcode and Authentication Requirements policy (IT-101), passwords must be at least 12 characters long and changed every 90 days."
                else:
                    response_text = ACCESS_OR_COVERAGE_REFUSAL
            elif "code review" in low_msg or "developer" in low_msg:
                if context_contains_dev:
                    response_text = "According to the Developer Handbook (DEV-101), pull requests require at least two senior engineer approvals before merging."
                else:
                    response_text = ACCESS_OR_COVERAGE_REFUSAL
            else:
                response_text = SOURCE_COVERAGE_REFUSAL
        else:
            # General Chat flow: direct answers
            if "hello" in low_msg or "hi" in low_msg:
                response_text = "Hello! I am AskGovRAGBot, your governed compliance assistant. How can I help you today?"
            elif "france" in low_msg:
                response_text = "The capital of France is Paris."
            elif "records" in low_msg and "ledger" in low_msg:
                response_text = "There are multiple records logged in the audit ledger database."
            else:
                response_text = "This is a mock response from AskGovRAGBot. [MOCK_ANSWER]"
                
        ai_message = AIMessage(content=response_text)
        return ChatResult(generations=[ChatGeneration(message=ai_message)])

    @property
    def _llm_type(self) -> str:
        return "fallback-offline-chat"

_LLM_THROTTLE_STATE = {"last_call": 0.0}

class RateLimitedChatModel(BaseChatModel):
    inner: BaseChatModel
    min_interval: float = 3.5

    def __init__(self, inner: BaseChatModel, min_interval: float = 3.5, **kwargs):
        super().__init__(inner=inner, min_interval=min_interval, **kwargs)

    def _throttle(self):
        import time
        now = time.time()
        elapsed = now - _LLM_THROTTLE_STATE["last_call"]
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)
        _LLM_THROTTLE_STATE["last_call"] = time.time()

    def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        self._throttle()
        return self.inner._generate(messages, stop, run_manager, **kwargs)

    async def _agenerate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        self._throttle()
        return await self.inner._agenerate(messages, stop, run_manager, **kwargs)

    @property
    def _llm_type(self) -> str:
        return f"rate-limited-{self.inner._llm_type}"

def get_chat_model() -> BaseChatModel:
    """Instantiates and returns the configured ChatModel based on settings."""
    provider = settings.LLM_PROVIDER
    model_name = settings.LLM_MODEL
    
    def is_valid_key(key: str) -> bool:
        return bool(key and not key.startswith("your_") and key.strip() != "")
    
    if provider == "gemini":
        if not is_valid_key(settings.GOOGLE_API_KEY):
            print("[INFO] Valid GOOGLE_API_KEY not found. Using FallbackOfflineChatModel.")
            return FallbackOfflineChatModel()
        from langchain_google_genai import ChatGoogleGenerativeAI
        return ChatGoogleGenerativeAI(
            model=model_name,
            google_api_key=settings.GOOGLE_API_KEY,
            temperature=0.0
        )
        
    elif provider == "openai":
        if not is_valid_key(settings.OPENAI_API_KEY):
            print("[INFO] Valid OPENAI_API_KEY not found. Using FallbackOfflineChatModel.")
            return FallbackOfflineChatModel()
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model_name=model_name,
            openai_api_key=settings.OPENAI_API_KEY,
            temperature=0.0
        )
        
    elif provider == "nebius":
        if not is_valid_key(settings.OPENAI_API_KEY):
            print("[INFO] Valid OPENAI_API_KEY not found for Nebius. Using FallbackOfflineChatModel.")
            return FallbackOfflineChatModel()
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            base_url="https://api.nebius.ai/v1",
            model_name=model_name,
            openai_api_key=settings.OPENAI_API_KEY,
            temperature=0.0
        )
        
    elif provider == "cohere":
        if not is_valid_key(settings.COHERE_API_KEY):
            print("[INFO] Valid COHERE_API_KEY not found for Cohere. Using FallbackOfflineChatModel.")
            return FallbackOfflineChatModel()
        from langchain_cohere import ChatCohere
        cohere_model = ChatCohere(
            model=model_name if model_name else "command-r-08-2024",
            cohere_api_key=settings.COHERE_API_KEY,
            temperature=0.0
        )
        return RateLimitedChatModel(cohere_model, min_interval=3.5)
        
    return FallbackOfflineChatModel()
