from typing import Optional
from openreview_ai.providers.base import BaseLLMProvider
from openreview_ai.providers.ollama import OllamaProvider
from openreview_ai.providers.huggingface import HuggingFaceProvider
from openreview_ai.providers.openai_compat import OpenAICompatibleProvider
from openreview_ai.providers.mock_provider import MockSimulationProvider


def get_provider(
    provider_type: str,
    model_name: str,
    base_url: Optional[str] = None,
    api_key: Optional[str] = None,
    **kwargs
) -> BaseLLMProvider:
    """
    Factory function to instantiate the requested LLM provider.
    Supported types: 'ollama', 'huggingface', 'openai_compat', 'mock'
    """
    p_type = provider_type.lower()
    
    if p_type == "ollama":
        url = base_url or "http://localhost:11434"
        return OllamaProvider(model_name=model_name, base_url=url, **kwargs)
        
    elif p_type in ("huggingface", "hf"):
        return HuggingFaceProvider(model_name=model_name, token=api_key, **kwargs)
        
    elif p_type in ("openai_compat", "groq", "deepseek", "vllm", "lmstudio"):
        return OpenAICompatibleProvider(model_name=model_name, base_url=base_url, api_key=api_key, **kwargs)
        
    elif p_type in ("mock", "simulate", "demo"):
        return MockSimulationProvider(model_name=model_name, **kwargs)
        
    else:
        raise ValueError(f"Unknown provider type '{provider_type}'. Must be one of: ollama, huggingface, openai_compat, mock")
