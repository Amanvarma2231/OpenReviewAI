from abc import ABC, abstractmethod
from typing import List, Optional


class BaseLLMProvider(ABC):
    """Abstract base class for all LLM providers (Ollama, HuggingFace, OpenAI-compatible, Mock)."""
    
    def __init__(self, model_name: str, **kwargs):
        self.model_name = model_name
        self.kwargs = kwargs

    @abstractmethod
    def generate(self, system_prompt: str, user_prompt: str, temperature: float = 0.2) -> str:
        """Generates a text completion given system and user prompts."""
        pass

    @abstractmethod
    def check_health(self) -> bool:
        """Checks if the provider endpoint is accessible."""
        pass

    def get_available_models(self) -> List[str]:
        """Returns list of models available through this provider."""
        return [self.model_name]
