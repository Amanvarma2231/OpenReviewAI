import os
from typing import Optional
from openreview_ai.providers.base import BaseLLMProvider


class HuggingFaceProvider(BaseLLMProvider):
    """
    Hugging Face Inference API Provider for open-source models.
    Supports Gemma, Mistral, Qwen, DeepSeek hosted on Hugging Face.
    """

    def __init__(self, model_name: str, token: Optional[str] = None, **kwargs):
        super().__init__(model_name, **kwargs)
        self.token = token or os.getenv("HUGGINGFACEHUB_API_TOKEN") or os.getenv("HF_TOKEN")

    def check_health(self) -> bool:
        return bool(self.token)

    def generate(self, system_prompt: str, user_prompt: str, temperature: float = 0.2) -> str:
        try:
            from huggingface_hub import InferenceClient
        except ImportError:
            raise ImportError("huggingface-hub is required for HuggingFaceProvider. Run: pip install huggingface-hub")

        client = InferenceClient(model=self.model_name, token=self.token)
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]

        try:
            response = client.chat_completion(
                messages=messages,
                temperature=temperature,
                max_tokens=2048
            )
            return response.choices[0].message.content
        except Exception as e:
            raise RuntimeError(f"Hugging Face Inference error for model '{self.model_name}': {str(e)}")
