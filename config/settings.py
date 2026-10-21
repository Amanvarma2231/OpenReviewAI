"""
OpenReview AI - Configuration Settings
=====================================
Centralized, validated configuration settings backed by pydantic and .env support.
"""

import os
from pathlib import Path
from typing import Optional, List
from pydantic import BaseModel, Field

try:
    from dotenv import load_dotenv
    # Load .env file from project root if it exists
    load_dotenv()
except ImportError:
    pass

# Base project directory
PROJECT_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseModel):
    # Ollama settings
    ollama_base_url: str = Field(
        default_factory=lambda: os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
    )
    ollama_timeout_seconds: int = Field(
        default_factory=lambda: int(os.getenv("OLLAMA_TIMEOUT_SECONDS", "120"))
    )

    # Models (independent configuration)
    generator_model: str = Field(
        default_factory=lambda: os.getenv("GENERATOR_MODEL", "qwen2.5-coder:3b")
    )
    reviewer_model: str = Field(
        default_factory=lambda: os.getenv("REVIEWER_MODEL", "deepseek-coder:1.3b")
    )

    # Supported/recommended models list for UI selection
    recommended_generators: List[str] = [
        "qwen2.5-coder:3b",
        "qwen2.5-coder:1.5b",
        "qwen2.5-coder:0.5b",
        "qwen2.5-coder:7b",
        "deepseek-coder:1.3b",
        "codellama:7b",
    ]
    recommended_reviewers: List[str] = [
        "deepseek-coder:1.3b",
        "qwen2.5-coder:1.5b",
        "qwen2.5-coder:3b",
        "deepseek-coder:6.7b",
        "codellama:7b",
    ]

    # Workflow controller settings
    default_max_retries: int = Field(
        default_factory=lambda: int(os.getenv("DEFAULT_MAX_RETRIES", "3"))
    )
    max_allowed_retries: int = Field(
        default_factory=lambda: int(os.getenv("MAX_ALLOWED_RETRIES", "5"))
    )

    # Sandbox and Testing settings
    safe_testing_mode: bool = Field(
        default_factory=lambda: os.getenv("SAFE_TESTING_MODE", "True").lower() in ("true", "1", "yes")
    )
    test_timeout_seconds: int = Field(
        default_factory=lambda: int(os.getenv("TEST_TIMEOUT_SECONDS", "10"))
    )
    enable_ruff: bool = Field(
        default_factory=lambda: os.getenv("ENABLE_RUFF", "True").lower() in ("true", "1", "yes")
    )

    # Storage paths
    runs_dir: Path = Field(
        default_factory=lambda: PROJECT_ROOT / os.getenv("RUNS_DIR", "outputs/runs")
    )
    reports_dir: Path = Field(
        default_factory=lambda: PROJECT_ROOT / os.getenv("REPORTS_DIR", "outputs/reports")
    )
    code_dir: Path = Field(
        default_factory=lambda: PROJECT_ROOT / os.getenv("CODE_DIR", "outputs/code")
    )

    log_level: str = Field(
        default_factory=lambda: os.getenv("LOG_LEVEL", "INFO")
    )

    def ensure_directories(self) -> None:
        """Creates output directories if they do not exist."""
        self.runs_dir.mkdir(parents=True, exist_ok=True)
        self.reports_dir.mkdir(parents=True, exist_ok=True)
        self.code_dir.mkdir(parents=True, exist_ok=True)


# Global singleton cache
_settings: Optional[Settings] = None


def get_settings(reload: bool = False) -> Settings:
    """Returns the cached Settings instance or creates a new one."""
    global _settings
    if _settings is None or reload:
        _settings = Settings()
        _settings.ensure_directories()
    return _settings
