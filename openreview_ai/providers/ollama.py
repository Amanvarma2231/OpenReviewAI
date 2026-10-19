import requests
from typing import List, Optional
from openreview_ai.providers.base import BaseLLMProvider


class OllamaProvider(BaseLLMProvider):
    """
    Direct HTTP client for local Ollama server.
    Supports all open-source models (Gemma, Mistral, Qwen, DeepSeek, etc.).
    """

    def __init__(self, model_name: str, base_url: str = "http://localhost:11434", timeout: int = 60, **kwargs):
        super().__init__(model_name, **kwargs)
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def check_health(self) -> bool:
        """Verifies if Ollama server is responsive."""
        try:
            res = requests.get(f"{self.base_url}/api/tags", timeout=3)
            return res.status_code == 200
        except Exception:
            return False

    def get_available_models(self) -> List[str]:
        """Fetches all downloaded models in local Ollama instance."""
        try:
            res = requests.get(f"{self.base_url}/api/tags", timeout=3)
            if res.status_code == 200:
                data = res.json()
                return [m["name"] for m in data.get("models", [])]
        except Exception:
            pass
        return []

    def generate(self, system_prompt: str, user_prompt: str, temperature: float = 0.2) -> str:
        """Generates chat completion via Ollama /api/chat."""
        payload = {
            "model": self.model_name,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "options": {
                "temperature": temperature,
            },
            "stream": False
        }

        try:
            res = requests.post(
                f"{self.base_url}/api/chat",
                json=payload,
                timeout=self.timeout
            )
            if res.status_code != 200:
                err_detail = res.text
                try:
                    err_json = res.json()
                    err_detail = err_json.get("error", res.text)
                except Exception:
                    pass
                raise RuntimeError(f"Ollama server error ({res.status_code}): {err_detail}")
            data = res.json()
            return data.get("message", {}).get("content", "")
        except requests.exceptions.RequestException as e:
            raise ConnectionError(
                f"Failed to communicate with Ollama at {self.base_url} for model '{self.model_name}': {str(e)}"
            )
