"""
OllamaProvider — Enhanced HTTP client for local Ollama server.
Includes smart health-check, model availability detection, and
graceful error handling with informative messages.
"""
import requests
from typing import List, Optional
from openreview_ai.providers.base import BaseLLMProvider


class OllamaProvider(BaseLLMProvider):
    """
    Direct HTTP client for local Ollama server.
    Supports Gemma, Mistral, Qwen, DeepSeek, Bonsai, and any
    Ollama-compatible open-source model.
    """

    def __init__(
        self,
        model_name: str,
        base_url: str = "http://localhost:11434",
        timeout: int = 90,
        **kwargs,
    ):
        super().__init__(model_name, **kwargs)
        self.base_url = base_url.rstrip("/")
        self.timeout  = timeout

    # ── Public API ────────────────────────────────────────────────

    def check_health(self) -> bool:
        """Returns True if the Ollama REST API is reachable."""
        try:
            res = requests.get(f"{self.base_url}/api/tags", timeout=4)
            return res.status_code == 200
        except Exception:
            return False

    def get_available_models(self) -> List[str]:
        """Returns list of locally-downloaded Ollama model names."""
        try:
            res = requests.get(f"{self.base_url}/api/tags", timeout=4)
            if res.status_code == 200:
                data = res.json()
                return [m["name"] for m in data.get("models", [])]
        except Exception:
            pass
        return []

    def model_is_available(self) -> bool:
        """Returns True if this provider's model is pulled and available."""
        available = self.get_available_models()
        name = self.model_name.lower()
        return any(name == m.lower() or name in m.lower() for m in available)

    def generate(
        self,
        system_prompt: str,
        user_prompt:   str,
        temperature:   float = 0.2,
    ) -> str:
        """
        Generates a chat completion via Ollama /api/chat endpoint.
        Raises RuntimeError or ConnectionError with clear actionable messages.
        """
        if not self.check_health():
            raise ConnectionError(
                "Ollama server is not reachable at "
                f"{self.base_url}.\n\n"
                "➡️  Solutions:\n"
                "   1. Start Ollama Desktop, or run `ollama serve` in a terminal.\n"
                "   2. Switch to '⚡ Smart Simulator' in the sidebar for instant demo (no GPU needed)."
            )

        if not self.model_is_available():
            available = self.get_available_models()
            avail_str = ", ".join(available) if available else "(none downloaded)"
            raise RuntimeError(
                f"Model '{self.model_name}' is not pulled locally.\n\n"
                f"   Downloaded models: {avail_str}\n\n"
                "➡️  Solutions:\n"
                f"   1. Use the sidebar 'Pull Model' panel to download '{self.model_name}'.\n"
                f"   2. Or run: ollama pull {self.model_name}\n"
                "   3. Or switch to '⚡ Smart Simulator' to demo without any download."
            )

        payload = {
            "model": self.model_name,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_prompt},
            ],
            "options": {"temperature": temperature},
            "stream":  False,
        }

        try:
            res = requests.post(
                f"{self.base_url}/api/chat",
                json=payload,
                timeout=self.timeout,
            )
        except requests.exceptions.Timeout:
            raise TimeoutError(
                f"Ollama timed out after {self.timeout}s generating with '{self.model_name}'.\n"
                "Try a smaller/faster model, or increase the timeout."
            )
        except requests.exceptions.ConnectionError as e:
            raise ConnectionError(
                f"Lost connection to Ollama at {self.base_url}: {e}\n"
                "Ensure `ollama serve` is running and the port is not blocked."
            )

        if res.status_code != 200:
            try:
                err_detail = res.json().get("error", res.text)
            except Exception:
                err_detail = res.text
            raise RuntimeError(
                f"Ollama HTTP {res.status_code}: {err_detail}\n\n"
                "➡️  If the error mentions 'llama-server not found', your Ollama\n"
                "   installation may be incomplete. Re-install from https://ollama.com/\n"
                "   or switch to '⚡ Smart Simulator' in the sidebar."
            )

        data = res.json()
        return data.get("message", {}).get("content", "")
