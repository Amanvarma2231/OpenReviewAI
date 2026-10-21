"""
OpenReview AI - Review Loop Module
==================================
Convenience helper interface around the WorkflowController.
"""

from typing import List, Optional, Callable
from models.schemas import WorkflowReport
from workflow.controller import WorkflowController


def execute_review_loop(
    task: str,
    constraints: Optional[List[str]] = None,
    test_code: Optional[str] = None,
    max_attempts: int = 3,
    generator_model: Optional[str] = None,
    reviewer_model: Optional[str] = None,
    mock_mode: bool = False,
    progress_callback: Optional[Callable[[str, int, str], None]] = None,
) -> WorkflowReport:
    """Convenience functional wrapper to run a complete review and correction workflow."""
    from utils.ollama_client import OllamaClient
    from agents.generator import GeneratorAgent
    from agents.reviewer import ReviewerAgent
    from config.settings import get_settings

    settings = get_settings()
    client = OllamaClient(
        base_url=settings.ollama_base_url,
        timeout=settings.ollama_timeout_seconds,
        mock_mode=mock_mode,
    )

    gen_model = generator_model or settings.generator_model
    rev_model = reviewer_model or settings.reviewer_model

    generator = GeneratorAgent(client=client, model_name=gen_model)
    reviewer = ReviewerAgent(client=client, model_name=rev_model)

    controller = WorkflowController(
        client=client,
        generator=generator,
        reviewer=reviewer,
        settings=settings,
    )

    return controller.run(
        task=task,
        constraints=constraints,
        test_code=test_code,
        max_attempts=max_attempts,
        progress_callback=progress_callback,
    )
