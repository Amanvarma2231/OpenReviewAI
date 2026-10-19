import argparse
import sys
import io

# Ensure UTF-8 output on Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table
from rich.markdown import Markdown

from openreview_ai.config import WorkflowConfig
from openreview_ai.engine import WorkflowOrchestrator
from openreview_ai.utils.diff_viewer import compute_unified_diff
from openreview_ai.utils.report_exporter import export_markdown_report
from openreview_ai.providers.ollama import OllamaProvider

console = Console(force_terminal=True, legacy_windows=False)


def build_banner():
    banner = """[bold cyan]+----------------------------------------------------------------------------+
|            OpenReviewAI: Multi-LLM Code Review & Fix Loop                  |
|     Open-Source Models: Gemma * Mistral * Bonsai * Qwen * DeepSeek         |
+----------------------------------------------------------------------------+[/bold cyan]"""
    console.print(banner)


def main():
    build_banner()

    parser = argparse.ArgumentParser(description="Multi-LLM Code Review and Correction Engine")
    parser.add_argument("--prompt", "-p", type=str, help="Coding task requirement")
    parser.add_argument("--file", "-f", type=str, default=None, help="Existing Python file path to review and auto-fix")
    parser.add_argument("--provider", type=str, default=None, choices=["ollama", "huggingface", "openai_compat", "mock"], help="LLM Provider")
    parser.add_argument("--generator", "-g", type=str, default=None, help="LLM 1 (Generator) Model Name")
    parser.add_argument("--reviewer", "-r", type=str, default=None, help="LLM 2 (Reviewer) Model Name")
    parser.add_argument("--validator", "-v", type=str, default=None, help="LLM 3 (Validator) Model Name")
    parser.add_argument("--max-retries", "-m", type=int, default=3, help="Max review/fix retry limit")
    parser.add_argument("--tests", "-t", type=str, default=None, help="Unit tests code to enforce")
    parser.add_argument("--export", "-e", type=str, default="review_report.md", help="Export markdown report path")
    parser.add_argument("--demo", action="store_true", help="Run quick preconfigured offline simulation demo")

    args = parser.parse_args()

    existing_code = None
    if args.file:
        try:
            with open(args.file, "r", encoding="utf-8") as f:
                existing_code = f.read()
            console.print(f"[bold green][OK] Loaded file '{args.file}' for review and repair ({len(existing_code.splitlines())} lines).[/bold green]")
        except Exception as e:
            console.print(f"[bold red]Error reading file '{args.file}': {e}[/bold red]")
            sys.exit(1)

    # Determine Provider and models
    provider_type = args.provider
    if args.demo:
        provider_type = "mock"
        task_prompt = args.prompt or "Write a python function to check if a string is a palindrome."
    elif not provider_type:
        # Auto-detect Ollama
        ollama = OllamaProvider("check")
        if ollama.check_health():
            installed = ollama.get_available_models()
            if installed:
                provider_type = "ollama"
                console.print(f"[green][OK] Local Ollama detected with models: {', '.join(installed)}[/green]")
            else:
                provider_type = "mock"
                console.print("[yellow][INFO] Ollama active but no models pulled. Defaulting to Smart Simulation Mode.[/yellow]")
        else:
            provider_type = "mock"
            console.print("[yellow][INFO] Ollama not responding. Defaulting to Smart Simulation Mode.[/yellow]")

    task_prompt = args.prompt
    if not task_prompt:
        if existing_code:
            task_prompt = f"Audit and repair code from file: {args.file}"
        else:
            console.print("\n[bold yellow]Enter your coding task specification:[/bold yellow]")
            task_prompt = input(">>> ").strip()
            if not task_prompt:
                task_prompt = "Write a python function to calculate the factorial of a number."
                console.print(f"[dim]No prompt entered. Using default: '{task_prompt}'[/dim]")
        if not task_prompt:
            task_prompt = "Write a python function to calculate the factorial of a number."
            console.print(f"[dim]No prompt entered. Using default: '{task_prompt}'[/dim]")

    # Resolve models
    if provider_type == "ollama":
        ollama = OllamaProvider("check")
        avail = ollama.get_available_models()
        default_gen = "qwen2.5:0.5b" if "qwen2.5:0.5b" in avail else (avail[0] if avail else "qwen2.5:0.5b")
        default_rev = "deepseek-coder:1.3b" if "deepseek-coder:1.3b" in avail else default_gen
        default_val = default_rev
    else:
        default_gen = "qwen2.5:0.5b"
        default_rev = "mistral:latest"
        default_val = "deepseek-coder:1.3b"

    gen_model = args.generator or default_gen
    rev_model = args.reviewer or default_rev
    val_model = args.validator or default_val

    config = WorkflowConfig(
        provider_type=provider_type,
        generator_model=gen_model,
        reviewer_model=rev_model,
        validator_model=val_model,
        max_retries=args.max_retries,
        enable_third_llm_validator=True
    )

    console.print(Panel(
        f"[bold]Provider:[/bold] {config.provider_type}\n"
        f"[bold]LLM 1 (Generator):[/bold] {config.generator_model}\n"
        f"[bold]LLM 2 (Reviewer):[/bold] {config.reviewer_model}\n"
        f"[bold]LLM 3 (Validator):[/bold] {config.validator_model}\n"
        f"[bold]Max Retries:[/bold] {config.max_retries}\n"
        f"[bold]Task:[/bold] {task_prompt}",
        title="[bold green]Workflow Setup[/bold green]",
        border_style="green"
    ))

    # Event listener for rich live rendering
    previous_code_holder = {"code": None}

    def on_event(event_name: str, data: dict):
        if event_name == "generation_started":
            console.print(f"\n[cyan]🤖 Round {data.get('round')}: {data.get('agent')} is generating code...[/cyan]")
        elif event_name == "generation_completed":
            code = data.get("code", "")
            previous_code_holder["code"] = code
            syntax = Syntax(code, "python", theme="monokai", line_numbers=True)
            console.print(Panel(syntax, title=f"[bold]Round {data.get('round')} - Code by LLM 1[/bold]", border_style="cyan"))
        elif event_name == "execution_completed":
            success = data.get("success")
            icon = "[bold green]✔ PASSED[/bold green]" if success else "[bold red]✖ FAILED[/bold red]"
            console.print(f"  [dim]Sandbox Execution:[/dim] {icon}")
            if not success and data.get("stderr"):
                console.print(f"  [red]{data.get('stderr').strip()[:200]}[/red]")
        elif event_name == "review_completed":
            rev = data.get("review", {})
            status = rev.get("status")
            badge = "[green]APPROVED[/green]" if status == "APPROVED" else "[red]CHANGES_REQUESTED[/red]"
            console.print(f"  [bold]LLM 2 (Reviewer):[/bold] {badge} (Score: {rev.get('overall_score')}/10)")
            console.print(f"  [italic]{rev.get('summary')}[/italic]")
            bugs = rev.get("bugs", [])
            if bugs:
                table = Table(title=f"Bugs Flagged by LLM 2 (Round {data.get('round')})", show_lines=True)
                table.add_column("Line", style="cyan", width=6)
                table.add_column("Category", style="magenta", width=12)
                table.add_column("Severity", style="bold red", width=10)
                table.add_column("Description", style="white")
                table.add_column("Suggested Fix", style="green")
                for b in bugs:
                    table.add_row(
                        str(b.get("line_number") or "-"),
                        b.get("category", "LOGIC"),
                        b.get("severity", "MAJOR"),
                        b.get("description", ""),
                        b.get("suggested_fix", "")
                    )
                console.print(table)
        elif event_name == "validation_completed":
            val = data.get("validation", {})
            badge = "[green]APPROVED[/green]" if val.get("status") == "APPROVED" else "[yellow]FLAGGED[/yellow]"
            console.print(f"  [bold]LLM 3 (Validator):[/bold] {badge} | {val.get('summary')}")
        elif event_name == "fix_started":
            console.print(f"\n[bold yellow]>> Passing review feedback back to LLM 1... Fix cycle Round {data.get('round')}[/bold yellow]")
        elif event_name == "fix_completed":
            fixed_code = data.get("code", "")
            old_code = previous_code_holder["code"]
            if old_code:
                diff_text = compute_unified_diff(old_code, fixed_code, "Previous Version", "Fixed Version")
                if diff_text:
                    syntax_diff = Syntax(diff_text, "diff", theme="monokai")
                    console.print(Panel(syntax_diff, title="[bold]Code Refactoring Diff[/bold]", border_style="yellow"))
            previous_code_holder["code"] = fixed_code

    orchestrator = WorkflowOrchestrator(config=config)
    result = orchestrator.run(
        task_prompt=task_prompt,
        target_language="python",
        unit_tests=args.tests,
        existing_code=existing_code,
        on_event=on_event
    )

    # Final Summary Banner
    color = "green" if result.status == "APPROVED" else "yellow"
    console.print(Panel(
        f"[bold {color}]Workflow Finished: {result.status}[/bold {color}]\n"
        f"  - Total Iteration Rounds: [bold]{result.rounds_count}[/bold]\n"
        f"  - Total Bugs Flagged: [bold]{result.total_bugs_detected}[/bold]\n"
        f"  - Total Bugs Resolved: [bold]{result.total_bugs_fixed}[/bold]\n"
        f"  - Final Sandbox Execution: [bold]{'Success' if (result.final_execution and result.final_execution.success) else 'N/A'}[/bold]",
        title="[bold]Review Summary[/bold]",
        border_style=color
    ))

    # Export Report
    if args.export:
        report_md = export_markdown_report(result)
        with open(args.export, "w", encoding="utf-8") as f:
            f.write(report_md)
        console.print(f"[bold green][OK] Full audit report exported to: {args.export}[/bold green]\n")


if __name__ == "__main__":
    main()
