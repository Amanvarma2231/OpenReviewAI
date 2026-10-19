import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from openreview_ai.config import WorkflowConfig
from openreview_ai.engine import WorkflowOrchestrator


def main():
    print("=== OpenReviewAI: Basic Multi-LLM Review Example ===\n")
    
    # 1. Setup configuration
    config = WorkflowConfig(
        provider_type="mock",  # Can be 'ollama', 'huggingface', 'openai_compat', 'mock'
        generator_model="qwen2.5:0.5b",
        reviewer_model="mistral:latest",
        validator_model="deepseek-coder:1.3b",
        max_retries=3,
        enable_sandbox_execution=True
    )
    
    # 2. Instantiate orchestrator
    orchestrator = WorkflowOrchestrator(config=config)
    
    # 3. Run coding requirement
    task = "Write a python function to compute the factorial of an integer, handling edge cases."
    print(f"Task: {task}\n")
    
    result = orchestrator.run(task_prompt=task)
    
    # 4. Display result
    print(f"Workflow Finished With Status: {result.status}")
    print(f"Total Iteration Rounds: {result.rounds_count}")
    print(f"Bugs Flagged: {result.total_bugs_detected} | Bugs Resolved: {result.total_bugs_fixed}\n")
    print("Final Approved Code:")
    print("--------------------------------------------------")
    print(result.final_code)
    print("--------------------------------------------------")


if __name__ == "__main__":
    main()
