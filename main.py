"""
OpenReview AI — CLI Entrypoint
==============================
Command line interface to execute tasks, inspect local Ollama health, and view run statistics.
"""

import argparse
import sys
from pathlib import Path
from utils.ollama_client import OllamaClient
from config.settings import get_settings
from storage.history_store import HistoryStore
from storage.report_generator import generate_markdown_report
from workflow.review_loop import execute_review_loop


def main():
    parser = argparse.ArgumentParser(
        description="OpenReview AI — Multi-LLM Code Generation, Review & Self-Correction System"
    )
    parser.add_argument("--task", type=str, help="Python programming task to solve.")
    parser.add_argument("--test-file", type=str, help="Path to pytest file containing assertions.")
    parser.add_argument("--generator", type=str, help="Ollama model for code generator.")
    parser.add_argument("--reviewer", type=str, help="Ollama model for code reviewer.")
    parser.add_argument("--max-retries", type=int, default=3, help="Maximum review iterations (1-5).")
    parser.add_argument("--check-ollama", action="store_true", help="Check local Ollama server connectivity.")
    parser.add_argument("--stats", action="store_true", help="Display summary statistics of saved runs.")
    parser.add_argument("--mock", action="store_true", help="Run with mock LLM responses (offline/demo mode).")
    parser.add_argument("--output-report", type=str, help="Path to save generated Markdown report.")

    args = parser.parse_args()
    settings = get_settings()

    if args.check_ollama:
        print("\nChecking local Ollama status...")
        client = OllamaClient(base_url=settings.ollama_base_url, mock_mode=args.mock)
        health = client.check_health()
        print(f"Status:  {health.get('status')}")
        print(f"Version: {health.get('version')}")
        print(f"Message: {health.get('message')}")
        models = client.list_installed_models()
        print(f"Installed Models: {', '.join(models) if models else 'None found'}\n")
        return

    if args.stats:
        store = HistoryStore()
        stats = store.get_summary_stats()
        print("\n=== OpenReview AI Statistics ===")
        print(f"Total Runs:      {stats['total_runs']}")
        print(f"Passed Runs:     {stats['passed_runs']}")
        print(f"Failed Runs:     {stats['failed_runs']}")
        print(f"Pass Rate:       {stats['pass_rate_pct']}%")
        print(f"Avg Attempts:    {stats['avg_attempts']}")
        print(f"Avg Duration:    {stats['avg_duration_sec']}s\n")
        return

    if not args.task:
        parser.print_help()
        sys.exit(0)

    test_code = None
    if args.test_file:
        test_path = Path(args.test_file)
        if test_path.exists():
            test_code = test_path.read_text(encoding="utf-8")
        else:
            print(f"Warning: Test file {args.test_file} not found. Running without test suite.")

    def cli_progress(stage: str, attempt: int, msg: str):
        print(f"[{stage}] (Attempt {attempt}) -> {msg}")

    print("\nStarting OpenReview AI Workflow...")
    report = execute_review_loop(
        task=args.task,
        test_code=test_code,
        max_attempts=args.max_retries,
        generator_model=args.generator,
        reviewer_model=args.reviewer,
        mock_mode=args.mock,
        progress_callback=cli_progress,
    )

    print("\n" + "=" * 60)
    print(f"WORKFLOW COMPLETED: {report.final_status.value}")
    print(f"Stop Reason: {report.stop_reason}")
    print(f"Total Attempts: {report.total_attempts}")
    print(f"Total Duration: {report.total_duration_seconds:.2f}s")
    print("=" * 60)

    print("\n### Final Code:")
    print(report.final_code)

    if args.output_report:
        md_text = generate_markdown_report(report)
        Path(args.output_report).write_text(md_text, encoding="utf-8")
        print(f"\nReport written to {args.output_report}")


if __name__ == "__main__":
    main()
