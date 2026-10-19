import re
import json
from typing import Optional, Dict, Any, Tuple
from openreview_ai.providers.base import BaseLLMProvider


class BaseAgent:
    """Base class for multi-agent participants."""

    def __init__(self, role_name: str, provider: BaseLLMProvider):
        self.role_name = role_name
        self.provider = provider

    @property
    def model_name(self) -> str:
        return self.provider.model_name

    @staticmethod
    def extract_code_block(text: str, language: str = "python") -> str:
        """
        Extracts code block from LLM markdown response.
        Falls back to raw text if no code blocks are found.
        """
        # Match ```python ... ``` or ``` ... ```
        pattern = rf"```(?:{language})?\s*\n(.*?)```"
        matches = re.findall(pattern, text, re.DOTALL | re.IGNORECASE)
        if matches:
            # Pick longest block
            longest = max(matches, key=len)
            return longest.strip()
            
        # Fallback: check if text has python def / class
        if "def " in text or "class " in text or "import " in text:
            return text.strip()
            
        return text.strip()

    @staticmethod
    def extract_json_block(text: str) -> Optional[Dict[str, Any]]:
        """
        Extracts JSON block from LLM response.
        Handles ```json ... ``` blocks as well as naked JSON objects.
        """
        # Attempt 1: Check markdown json code blocks
        json_pattern = r"```(?:json)?\s*\n(.*?)```"
        matches = re.findall(json_pattern, text, re.DOTALL | re.IGNORECASE)
        for m in matches:
            try:
                return json.loads(m.strip())
            except Exception:
                continue

        # Attempt 2: Search for outer curly braces { ... }
        brace_pattern = r"(\{[\s\S]*\})"
        match = re.search(brace_pattern, text)
        if match:
            try:
                return json.loads(match.group(1).strip())
            except Exception:
                pass

        return None
