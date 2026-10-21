"""
OpenReview AI - History Store
=============================
Persists and retrieves workflow executions, iteration snapshots, and final code.
Guarantees clean JSON persistence without leaking sensitive runtime tokens.
"""

import json
from pathlib import Path
from typing import List, Optional, Dict, Any
from models.schemas import WorkflowReport
from config.settings import get_settings
from utils.logging_config import setup_logger

logger = setup_logger("HistoryStore")


class HistoryStore:
    """Manages reading and writing of workflow execution histories and generated code."""

    def __init__(self, runs_dir: Optional[Path] = None, code_dir: Optional[Path] = None):
        settings = get_settings()
        self.runs_dir = Path(runs_dir or settings.runs_dir)
        self.code_dir = Path(code_dir or settings.code_dir)

        self.runs_dir.mkdir(parents=True, exist_ok=True)
        self.code_dir.mkdir(parents=True, exist_ok=True)

    def save_report(self, report: WorkflowReport) -> Path:
        """Saves a WorkflowReport model to a JSON file."""
        file_path = self.runs_dir / f"{report.run_id}.json"
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(report.model_dump_json(indent=2))
        logger.info(f"Saved workflow report to {file_path}")
        return file_path

    def load_report(self, run_id: str) -> Optional[WorkflowReport]:
        """Loads a WorkflowReport from disk by run_id."""
        file_path = self.runs_dir / f"{run_id}.json"
        if not file_path.exists():
            return None
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return WorkflowReport.model_validate(data)
        except Exception as e:
            logger.error(f"Failed to load run {run_id}: {e}")
            return None

    def list_runs(self) -> List[Dict[str, Any]]:
        """
        Lists all saved runs, sorted by descending start_time.
        Returns lightweight summary dictionaries for UI tables and history browsing.
        """
        runs = []
        for file in self.runs_dir.glob("*.json"):
            try:
                with open(file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                runs.append({
                    "run_id": data.get("run_id", file.stem),
                    "task": data.get("task_description", "Unknown Task")[:80],
                    "status": data.get("final_status", "UNKNOWN"),
                    "attempts": data.get("total_attempts", 0),
                    "max_attempts": data.get("max_attempts", 3),
                    "duration": round(data.get("total_duration_seconds", 0.0), 2),
                    "timestamp": data.get("start_time", ""),
                    "generator_model": data.get("generator_model", ""),
                    "reviewer_model": data.get("reviewer_model", ""),
                })
            except Exception as e:
                logger.warning(f"Skipping unreadable run file {file}: {e}")

        # Sort newest first
        runs.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
        return runs

    def delete_run(self, run_id: str) -> bool:
        """Deletes a run JSON file and associated code files."""
        run_file = self.runs_dir / f"{run_id}.json"
        deleted = False
        if run_file.exists():
            run_file.unlink()
            deleted = True

        # Clean associated code files
        for code_file in self.code_dir.glob(f"{run_id}*.py"):
            try:
                code_file.unlink()
            except OSError:
                pass

        return deleted

    def clear_all(self) -> int:
        """Deletes all saved run records."""
        count = 0
        for file in self.runs_dir.glob("*.json"):
            try:
                file.unlink()
                count += 1
            except OSError:
                pass
        for code_file in self.code_dir.glob("*.py"):
            try:
                code_file.unlink()
            except OSError:
                pass
        return count

    def save_code_iteration(self, run_id: str, iteration: int, code: str) -> Path:
        """Saves code snapshot for a specific iteration."""
        filename = f"{run_id}_iteration_{iteration}.py"
        path = self.code_dir / filename
        with open(path, "w", encoding="utf-8") as f:
            f.write(code)
        return path

    def save_final_code(self, run_id: str, code: str) -> Path:
        """Saves the final accepted or terminal code for a run."""
        filename = f"{run_id}_final.py"
        path = self.code_dir / filename
        with open(path, "w", encoding="utf-8") as f:
            f.write(code)
        return path

    def get_summary_stats(self) -> Dict[str, Any]:
        """Calculates authentic summary statistics based solely on actual saved runs."""
        runs = self.list_runs()
        total = len(runs)
        if total == 0:
            return {
                "total_runs": 0,
                "passed_runs": 0,
                "failed_runs": 0,
                "pass_rate_pct": 0.0,
                "avg_attempts": 0.0,
                "avg_duration_sec": 0.0,
            }

        passed = sum(1 for r in runs if r["status"] == "PASSED")
        failed = total - passed
        avg_attempts = sum(r["attempts"] for r in runs) / total
        avg_duration = sum(r["duration"] for r in runs) / total

        return {
            "total_runs": total,
            "passed_runs": passed,
            "failed_runs": failed,
            "pass_rate_pct": round((passed / total) * 100, 1),
            "avg_attempts": round(avg_attempts, 1),
            "avg_duration_sec": round(avg_duration, 1),
        }
