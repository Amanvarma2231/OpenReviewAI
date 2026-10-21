"""
OpenReview AI - Ollama API Client
=================================
Robust HTTP client for local Ollama instances (default: http://localhost:11434).
Features:
- Health and connectivity checks
- Model availability and list inspection
- Chat and generate completion requests with timeouts
- Comprehensive error handling and user-friendly diagnostics
- Optional mock mode for testing and demonstrations without Ollama installed
"""

import json
import time
from typing import Dict, Any, List, Optional
import requests
from requests.exceptions import ConnectionError, Timeout, RequestException

from utils.logging_config import setup_logger

logger = setup_logger("OllamaClient")


class OllamaError(Exception):
    """Base exception for Ollama client errors."""
    pass


class OllamaConnectionError(OllamaError):
    """Raised when Ollama server cannot be reached."""
    pass


class OllamaModelNotFoundError(OllamaError):
    """Raised when the requested model is not downloaded in Ollama."""
    pass


class OllamaTimeoutError(OllamaError):
    """Raised when an inference call times out."""
    pass


class OllamaClient:
    """
    Client for interacting with Ollama's local HTTP API.
    Guarantees no external paid APIs are called.
    """

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        timeout: int = 120,
        mock_mode: bool = False,
    ):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.mock_mode = mock_mode

    def check_health(self) -> Dict[str, Any]:
        """
        Checks if the Ollama server is reachable and running.
        Returns a dictionary with status, version, and error message if any.
        """
        if self.mock_mode:
            return {
                "status": "online",
                "version": "mock-0.1.0",
                "message": "Running in Mock / Demonstration Mode",
                "models": ["qwen2.5-coder:3b", "deepseek-coder:1.3b"],
            }

        try:
            resp = requests.get(f"{self.base_url}/api/version", timeout=4)
            if resp.status_code == 200:
                data = resp.json()
                return {
                    "status": "online",
                    "version": data.get("version", "unknown"),
                    "message": "Ollama server is active and responding.",
                }
            else:
                return {
                    "status": "error",
                    "version": None,
                    "message": f"Ollama returned HTTP status {resp.status_code}",
                }
        except ConnectionError:
            return {
                "status": "offline",
                "version": None,
                "message": (
                    f"Cannot connect to Ollama at {self.base_url}. "
                    "Ensure Ollama is installed and running (`ollama serve`)."
                ),
            }
        except Timeout:
            return {
                "status": "timeout",
                "version": None,
                "message": f"Connection to Ollama at {self.base_url} timed out.",
            }
        except Exception as e:
            return {
                "status": "error",
                "version": None,
                "message": f"Unexpected error connecting to Ollama: {str(e)}",
            }

    def list_installed_models(self) -> List[str]:
        """Returns a list of model names currently installed in Ollama."""
        if self.mock_mode:
            return ["qwen2.5-coder:3b", "deepseek-coder:1.3b", "qwen2.5-coder:1.5b"]

        try:
            resp = requests.get(f"{self.base_url}/api/tags", timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                models = [m.get("name") for m in data.get("models", []) if "name" in m]
                return models
            return []
        except Exception as e:
            logger.warning(f"Failed to fetch model tags from Ollama: {e}")
            return []

    def is_model_available(self, model_name: str) -> bool:
        """
        Checks if a given model tag is installed locally.
        Handles tag matching (e.g., 'qwen2.5-coder:3b' vs 'qwen2.5-coder:3b-latest').
        """
        installed = self.list_installed_models()
        if not installed:
            return False

        # Direct match or partial prefix match
        target = model_name.lower().strip()
        for m in installed:
            m_lower = m.lower()
            if m_lower == target or m_lower.startswith(f"{target}:") or target.startswith(f"{m_lower}:"):
                return True
        return False

    def chat(
        self,
        model: str,
        messages: List[Dict[str, str]],
        temperature: float = 0.2,
        max_tokens: Optional[int] = None,
        json_format: bool = False,
    ) -> str:
        """
        Sends a chat completion request to Ollama (/api/chat).
        Sequential execution: Wait for completion before returning.
        """
        if self.mock_mode:
            return self._mock_chat_response(model, messages, json_format=json_format)

        # Pre-flight check: is Ollama running?
        health = self.check_health()
        if health["status"] != "online":
            raise OllamaConnectionError(health["message"])

        # Check model availability
        if not self.is_model_available(model):
            installed = self.list_installed_models()
            raise OllamaModelNotFoundError(
                f"Model '{model}' is not installed in Ollama. "
                f"Please run `ollama pull {model}` in your terminal. "
                f"Currently installed models: {installed or 'None'}"
            )

        payload: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": temperature,
            },
        }

        if max_tokens:
            payload["options"]["num_predict"] = max_tokens

        if json_format:
            payload["format"] = "json"

        endpoint = f"{self.base_url}/api/chat"
        logger.info(f"Sending request to Ollama [{model}] (timeout={self.timeout}s)...")
        start_time = time.time()

        try:
            resp = requests.post(
                endpoint,
                json=payload,
                timeout=self.timeout,
            )
            elapsed = time.time() - start_time

            if resp.status_code == 200:
                data = resp.json()
                content = data.get("message", {}).get("content", "")
                logger.info(f"Ollama [{model}] responded in {elapsed:.2f}s ({len(content)} chars)")
                return content
            else:
                error_text = resp.text
                raise OllamaError(
                    f"Ollama returned HTTP error {resp.status_code}: {error_text}"
                )
        except ConnectionError as e:
            raise OllamaConnectionError(
                f"Connection to Ollama lost at {endpoint}: {str(e)}"
            ) from e
        except Timeout as e:
            raise OllamaTimeoutError(
                f"Ollama inference timed out after {self.timeout} seconds. "
                "The model might be too large for available RAM or processing power."
            ) from e
        except RequestException as e:
            raise OllamaError(f"HTTP request error communicating with Ollama: {str(e)}") from e

    def _mock_chat_response(
        self,
        model: str,
        messages: List[Dict[str, str]],
        json_format: bool = False,
    ) -> str:
        """Generates realistic responses for tests or demo runs without live LLM."""
        user_msg = ""
        for m in reversed(messages):
            if m.get("role") == "user":
                user_msg = m.get("content", "")
                break

        is_review = (
            json_format
            or (messages and "adversarial" in messages[0].get("content", "").lower())
            or "output your strict json review:" in user_msg.lower()
            or "review" in model.lower()
        )

        # If this is reviewer model or prompt asks for JSON review
        if is_review:
            # Check if code inside prompt has an explicit mock bug marker
            if "TODO" in user_msg or "# BUG" in user_msg or "FAIL_TEST" in user_msg:
                return json.dumps({
                    "verdict": "FAIL",
                    "summary": "Mock Reviewer: The code contains incomplete logic or unresolved placeholders.",
                    "issues": [
                        {
                            "issue_type": "logic",
                            "severity": "HIGH",
                            "line_number": 3,
                            "description": "Unresolved placeholder or logic error detected in implementation.",
                            "suggested_fix": "Complete the implementation and handle empty inputs."
                        }
                    ],
                    "suggested_fixes": ["Replace placeholder with robust logic."],
                    "requirements_met": False,
                    "unresolved_concerns": ["Edge cases for zero or negative numbers"]
                })
            else:
                return json.dumps({
                    "verdict": "PASS",
                    "summary": "Mock Reviewer: The code is clean, syntactically correct, and satisfies all requirements.",
                    "issues": [],
                    "suggested_fixes": ["Optional: Add type hints for all parameters."],
                    "requirements_met": True,
                    "unresolved_concerns": []
                })

        # Otherwise it's generator
        if "fibonacci" in user_msg.lower():
            return (
                "```python\n"
                "def fibonacci(n: int) -> int:\n"
                "    \"\"\"Return the nth Fibonacci number.\"\"\"\n"
                "    if n < 0:\n"
                "        raise ValueError('n must be non-negative')\n"
                "    if n in (0, 1):\n"
                "        return n\n"
                "    a, b = 0, 1\n"
                "    for _ in range(2, n + 1):\n"
                "        a, b = b, a + b\n"
                "    return b\n"
                "```"
            )

        # Default generator response
        return (
            "```python\n"
            "def solution(*args, **kwargs):\n"
            "    \"\"\"Generated solution based on user task.\"\"\"\n"
            "    return True\n"
            "```"
        )
