"""
OpenReview AI - Safe Project Workspace & Archive Manager
========================================================
Provides secure file extraction, traversal rejection, manifest generation,
and isolated patch application for multi-file Python projects.
"""

import os
import io
import re
import shutil
import zipfile
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

# Security Constraints
MAX_TOTAL_FILES = 150
MAX_ARCHIVE_SIZE_BYTES = 15 * 1024 * 1024       # 15 MB
MAX_SINGLE_FILE_BYTES = 2 * 1024 * 1024          # 2 MB
MAX_TOTAL_UNCOMPRESSED_BYTES = 30 * 1024 * 1024  # 30 MB

# Blocked and Excluded Paths / Files
EXCLUDED_DIR_NAMES = {
    ".git", ".svn", ".hg", "__pycache__", ".pytest_cache", ".ruff_cache",
    ".mypy_cache", ".venv", "venv", "env", "node_modules", ".idea", ".vscode"
}

EXCLUDED_EXTENSIONS = {
    ".pyc", ".pyo", ".pyd", ".so", ".dll", ".dylib", ".exe", ".bin",
    ".whl", ".egg", ".tar", ".gz", ".rar", ".7z", ".iso", ".sqlite3", ".db"
}

SECRET_PATTERNS = [
    re.compile(r"^\.env.*", re.IGNORECASE),
    re.compile(r".*\.pem$", re.IGNORECASE),
    re.compile(r".*\.key$", re.IGNORECASE),
    re.compile(r".*id_rsa.*", re.IGNORECASE),
    re.compile(r".*credentials.*", re.IGNORECASE),
]


class SecurityValidationError(Exception):
    """Raised when an uploaded file or archive violates security constraints."""
    pass


class SafeProjectWorkspace:
    """
    Manages an isolated workspace for inspecting and improving multi-file projects.
    Guarantees that untrusted archives cannot escape their temporary directory.
    """

    def __init__(self, workspace_root: Optional[Path] = None):
        self.temp_dir = tempfile.mkdtemp(prefix="openreview_proj_")
        self.root = Path(workspace_root or self.temp_dir)
        self.original_dir = self.root / "original"
        self.working_dir = self.root / "working"
        self.original_dir.mkdir(parents=True, exist_ok=True)
        self.working_dir.mkdir(parents=True, exist_ok=True)
        self.manifest: List[Dict[str, Any]] = []

    def close(self):
        """Cleans up the temporary directory."""
        if Path(self.temp_dir).exists():
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    @staticmethod
    def is_path_safe(base_dir: Path, target_path: Path) -> bool:
        """Verifies that target_path resolves strictly within base_dir (prevents Zip Slip)."""
        try:
            resolved_base = base_dir.resolve()
            resolved_target = target_path.resolve()
            return resolved_target == resolved_base or resolved_base in resolved_target.parents
        except Exception:
            return False

    def ingest_zip(self, zip_bytes: bytes) -> List[Dict[str, Any]]:
        """
        Safely inspects and extracts a ZIP archive into the workspace original directory.
        Rejects Zip Slip, symlinks, oversized archives, and hazardous files.
        """
        if len(zip_bytes) > MAX_ARCHIVE_SIZE_BYTES:
            raise SecurityValidationError(
                f"Archive size ({len(zip_bytes)} bytes) exceeds safety limit of {MAX_ARCHIVE_SIZE_BYTES} bytes (15MB)."
            )

        try:
            zip_buffer = io.BytesIO(zip_bytes)
            with zipfile.ZipFile(zip_buffer, "r") as zf:
                infolist = zf.infolist()

                if len(infolist) > MAX_TOTAL_FILES:
                    raise SecurityValidationError(
                        f"Archive contains {len(infolist)} entries, exceeding limit of {MAX_TOTAL_FILES} files."
                    )

                total_uncompressed = sum(info.file_size for info in infolist)
                if total_uncompressed > MAX_TOTAL_UNCOMPRESSED_BYTES:
                    raise SecurityValidationError(
                        f"Uncompressed size ({total_uncompressed} bytes) exceeds limit of {MAX_TOTAL_UNCOMPRESSED_BYTES} bytes."
                    )

                extracted_count = 0
                for info in infolist:
                    filename = info.filename

                    # 1. Reject absolute paths or traversal attempts
                    if filename.startswith("/") or filename.startswith("\\") or ".." in filename.split("/"):
                        raise SecurityValidationError(f"Path traversal attempt detected in entry: {filename}")

                    # 2. Reject symlinks
                    # Unix symlink attribute flag is 0o120000
                    if (info.external_attr >> 16) & 0o120000 == 0o120000:
                        raise SecurityValidationError(f"Symlink detected and rejected for security: {filename}")

                    # 3. Check individual file size
                    if info.file_size > MAX_SINGLE_FILE_BYTES:
                        raise SecurityValidationError(
                            f"File '{filename}' exceeds individual size limit of {MAX_SINGLE_FILE_BYTES} bytes."
                        )

                    # 4. Check directory and secret exclusions
                    parts = Path(filename).parts
                    if any(part in EXCLUDED_DIR_NAMES for part in parts):
                        continue

                    stem_and_name = Path(filename).name
                    if any(pat.match(stem_and_name) for pat in SECRET_PATTERNS):
                        continue

                    ext = Path(filename).suffix.lower()
                    if ext in EXCLUDED_EXTENSIONS:
                        continue

                    # If directory, just skip or create
                    if info.is_dir():
                        continue

                    target_dest = self.original_dir / filename
                    if not self.is_path_safe(self.original_dir, target_dest):
                        raise SecurityValidationError(f"Unsafe destination path resolved: {target_dest}")

                    target_dest.parent.mkdir(parents=True, exist_ok=True)
                    with zf.open(info) as src, open(target_dest, "wb") as dst:
                        shutil.copyfileobj(src, dst)

                    extracted_count += 1

        except zipfile.BadZipFile:
            raise SecurityValidationError("The uploaded file is not a valid ZIP archive.")

        # Replicate original into working directory
        self._sync_original_to_working()
        self.manifest = self.build_manifest()
        return self.manifest

    def ingest_single_file(self, filename: str, content: str) -> List[Dict[str, Any]]:
        """Ingests a single source code file into the workspace."""
        clean_name = Path(filename).name
        if not clean_name.endswith((".py", ".txt", ".pyw")):
            clean_name += ".py"

        target_file = self.original_dir / clean_name
        with open(target_file, "w", encoding="utf-8") as f:
            f.write(content)

        self._sync_original_to_working()
        self.manifest = self.build_manifest()
        return self.manifest

    def _sync_original_to_working(self):
        """Duplicates clean original files to working directory."""
        if self.working_dir.exists():
            shutil.rmtree(self.working_dir, ignore_errors=True)
        shutil.copytree(self.original_dir, self.working_dir)

    def build_manifest(self) -> List[Dict[str, Any]]:
        """Builds an audit manifest of all extracted project files."""
        manifest = []
        for p in self.working_dir.rglob("*"):
            if p.is_file():
                rel_path = p.relative_to(self.working_dir).as_posix()
                size_b = p.stat().st_size
                is_py = p.suffix.lower() in [".py", ".pyw"]
                is_test = is_py and ("test" in rel_path.lower() or p.name.startswith("test_"))

                line_count = 0
                if is_py or p.suffix.lower() in [".txt", ".md", ".json", ".yaml", ".yml", ".toml"]:
                    try:
                        line_count = len(p.read_text(encoding="utf-8", errors="replace").splitlines())
                    except Exception:
                        pass

                manifest.append({
                    "relative_path": rel_path,
                    "size_bytes": size_b,
                    "lines": line_count,
                    "is_python": is_py,
                    "is_test": is_test,
                })

        manifest.sort(key=lambda x: (not x["is_python"], x["relative_path"]))
        return manifest

    def read_working_file(self, relative_path: str) -> Optional[str]:
        """Reads content of a file from the working directory."""
        p = self.working_dir / relative_path
        if not self.is_path_safe(self.working_dir, p) or not p.exists() or not p.is_file():
            return None
        return p.read_text(encoding="utf-8", errors="replace")

    def write_working_file(self, relative_path: str, new_content: str) -> bool:
        """Overwrites a file in the working directory (preserving original untouched)."""
        p = self.working_dir / relative_path
        if not self.is_path_safe(self.working_dir, p):
            raise SecurityValidationError(f"Attempted write outside working directory: {relative_path}")
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(new_content, encoding="utf-8")
        return True

    def compute_project_diff(self) -> Dict[str, str]:
        """
        Computes unified diff for all files between original and working directory.
        Returns mapping of relative_path -> unified_diff_text.
        """
        import difflib
        diffs = {}
        for p_work in self.working_dir.rglob("*"):
            if p_work.is_file():
                rel = p_work.relative_to(self.working_dir).as_posix()
                p_orig = self.original_dir / rel

                work_lines = p_work.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)
                orig_lines = []
                if p_orig.exists():
                    orig_lines = p_orig.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)

                if orig_lines != work_lines:
                    diff = difflib.unified_diff(
                        orig_lines,
                        work_lines,
                        fromfile=f"a/{rel}",
                        tofile=f"b/{rel}"
                    )
                    diff_text = "".join(diff)
                    if diff_text.strip():
                        diffs[rel] = diff_text
        return diffs

    def export_improved_zip(self) -> bytes:
        """Packs the working directory into a downloadable ZIP archive."""
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            for p in self.working_dir.rglob("*"):
                if p.is_file():
                    rel = p.relative_to(self.working_dir)
                    zf.write(p, arcname=rel.as_posix())
        return buffer.getvalue()
