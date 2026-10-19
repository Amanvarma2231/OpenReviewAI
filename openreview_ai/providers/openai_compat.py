import os
from typing import Optional
from openreview_ai.providers.base import BaseLLMProvider


class OpenAICompatibleProvider(BaseLLMProvider):
    """
    OpenAI-Compatible provider for Open-Source models.
    Supports Groq, DeepSeek API, Together, vLLM, LM Studio, etc.
    """

    def __init__(
        self,
        model_name: str,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        **kwargs
    ):
        super().__init__(model_name, **kwargs)
        self.base_url = base_url or os.getenv("OPENAI_COMPATIBLE_BASE_URL") or "https://api.groq.com/openai/v1"
        self.api_key = api_key or os.getenv("OPENAI_COMPATIBLE_API_KEY") or os.getenv("GROQ_API_KEY") or "dummy-key"

    def check_health(self) -> bool:
        return bool(self.base_url)

    def generate(self, system_prompt: str, user_prompt: str, temperature: float = 0.2) -> str:
        try:
            from openai import OpenAI
        except ImportError:
            raise ImportError("openai package is required for OpenAICompatibleProvider. Run: pip install openai")

        client = OpenAI(base_url=self.base_url, api_key=self.api_key)
        try:
            response = client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=temperature,
            )
            return response.choices[0].message.content or ""
        except Exception as e:
            raise RuntimeError(f"OpenAI-Compatible API error ({self.base_url}) for '{self.model_name}': {str(e)}")
