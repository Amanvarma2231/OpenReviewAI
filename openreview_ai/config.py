import os
from dataclasses import dataclass, field
from typing import Dict, List
from dotenv import load_dotenv

load_dotenv()

# Pre-defined Open-Source Model families as specified by Druidot Consulting
OPENSOURCE_MODEL_FAMILIES = {
    "Gemma": [
        "gemma2:2b",
        "gemma2:9b",
        "gemma:2b",
        "gemma:7b",
        "google/gemma-2-2b-it",
        "google/gemma-2-9b-it"
    ],
    "Mistral": [
        "mistral:latest",
        "mistral:7b",
        "mistralai/Mistral-7B-Instruct-v0.3",
        "mistralai/Mixtral-8x7B-Instruct-v0.1"
    ],
    "Bonsai": [
        "bonsai:latest",
        "codebonsai:8b",
        "codellama:7b",
        "starcoder2:3b"
    ],
    "Qwen": [
        "qwen2.5:0.5b",
        "qwen2.5-coder:1.5b",
        "qwen2.5-coder:7b",
        "qwen2.5:1.5b",
        "Qwen/Qwen2.5-Coder-1.5B-Instruct",
        "Qwen/Qwen2.5-Coder-7B-Instruct"
    ],
    "DeepSeek": [
        "deepseek-coder:1.3b",
        "deepseek-coder:6.7b",
        "deepseek-r1:1.5b",
        "deepseek-r1:7b",
        "deepseek-ai/DeepSeek-Coder-V2-Lite-Instruct"
    ]
}

@dataclass
class WorkflowConfig:
    """Configuration settings for the Multi-LLM Review and Correction Workflow."""
    
    # Provider Settings
    provider_type: str = os.getenv("LLM_PROVIDER", "ollama")  # 'ollama', 'huggingface', 'openai_compat', 'mock'
    ollama_base_url: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    
    # Hugging Face Settings
    hf_token: str = os.getenv("HUGGINGFACEHUB_API_TOKEN", "")
    
    # OpenAI Compatible API (Groq / DeepSeek API / vLLM / LM Studio / OpenRouter)
    openai_compat_base_url: str = os.getenv("OPENAI_COMPATIBLE_BASE_URL", "")
    openai_compat_api_key: str = os.getenv("OPENAI_COMPATIBLE_API_KEY", "")
    
    # Default Models for Roles
    generator_model: str = os.getenv("DEFAULT_GENERATOR_MODEL", "qwen2.5:0.5b")
    reviewer_model: str = os.getenv("DEFAULT_REVIEWER_MODEL", "mistral:latest")
    validator_model: str = os.getenv("DEFAULT_VALIDATOR_MODEL", "deepseek-coder:latest")
    
    # Workflow Loop Controls
    max_retries: int = int(os.getenv("DEFAULT_MAX_RETRIES", "3"))
    sandbox_timeout_seconds: int = int(os.getenv("SANDBOX_TIMEOUT_SECONDS", "5"))
    enable_sandbox_execution: bool = True
    enable_syntax_check: bool = True
    enable_third_llm_validator: bool = True
    temperature: float = 0.2
    
    @classmethod
    def get_supported_model_list(cls) -> List[str]:
        """Flattened list of all supported open-source models."""
        models = []
        for family, family_models in OPENSOURCE_MODEL_FAMILIES.items():
            models.extend(family_models)
        return models
