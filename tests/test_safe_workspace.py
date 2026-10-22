"""
Tests for SafeProjectWorkspace: Archive inspection, path traversal protection,
symlink rejection, manifest generation, and ZIP export.
"""

import io
import zipfile
import pytest
from pathlib import Path
from openreview_ai.sandbox.safe_workspace import (
    SafeProjectWorkspace,
    SecurityValidationError,
    MAX_ARCHIVE_SIZE_BYTES
)


def create_test_zip(files_dict: dict) -> bytes:
    """Helper to construct in-memory ZIP archives."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, content in files_dict.items():
            zf.writestr(name, content)
    return buf.getvalue()


def test_safe_workspace_single_file_ingestion():
    with SafeProjectWorkspace() as ws:
        manifest = ws.ingest_single_file("calculator.py", "def add(a, b):\n    return a + b\n")
        assert len(manifest) == 1
        assert manifest[0]["relative_path"] == "calculator.py"
        assert manifest[0]["is_python"] is True
        assert manifest[0]["lines"] == 2

        content = ws.read_working_file("calculator.py")
        assert content == "def add(a, b):\n    return a + b\n"


def test_safe_workspace_zip_extraction_and_manifest():
    files = {
        "src/main.py": "def main():\n    print('Hello')\n",
        "tests/test_main.py": "def test_hello():\n    assert True\n",
        "README.md": "# Project Title\n",
        "src/.env": "SECRET_KEY=12345\n",             # Should be excluded
        "src/__pycache__/cache.pyc": "binary_content", # Should be excluded
    }
    zip_bytes = create_test_zip(files)

    with SafeProjectWorkspace() as ws:
        manifest = ws.ingest_zip(zip_bytes)
        paths = [m["relative_path"] for m in manifest]

        # Valid files extracted
        assert "src/main.py" in paths
        assert "tests/test_main.py" in paths
        assert "README.md" in paths

        # Excluded files filtered out
        assert "src/.env" not in paths
        assert "src/__pycache__/cache.pyc" not in paths

        # Test detection flag
        test_entries = [m for m in manifest if m["relative_path"] == "tests/test_main.py"]
        assert len(test_entries) == 1
        assert test_entries[0]["is_test"] is True


def test_zip_slip_traversal_blocked():
    """Verifies that archive entries with directory traversal are strictly blocked."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("../../etc/passwd", "root:x:0:0")
    evil_zip = buf.getvalue()

    with SafeProjectWorkspace() as ws:
        with pytest.raises(SecurityValidationError, match="Path traversal"):
            ws.ingest_zip(evil_zip)


def test_oversized_archive_blocked():
    """Verifies that archives exceeding maximum byte limits are rejected immediately."""
    fake_huge_bytes = b"0" * (MAX_ARCHIVE_SIZE_BYTES + 1024)
    with SafeProjectWorkspace() as ws:
        with pytest.raises(SecurityValidationError, match="Archive size"):
            ws.ingest_zip(fake_huge_bytes)


def test_working_file_modification_and_diff():
    """Verifies that editing a working file does not touch the original and generates a clean diff."""
    files = {
        "app.py": "def process():\n    return 1\n"
    }
    zip_bytes = create_test_zip(files)

    with SafeProjectWorkspace() as ws:
        ws.ingest_zip(zip_bytes)

        # Original content intact
        orig_content = (ws.original_dir / "app.py").read_text(encoding="utf-8")
        assert orig_content == "def process():\n    return 1\n"

        # Apply improvement to working file
        ws.write_working_file("app.py", "def process() -> int:\n    \"\"\"Improved.\"\"\"\n    return 1\n")

        # Compute diffs
        diffs = ws.compute_project_diff()
        assert "app.py" in diffs
        assert "+    \"\"\"Improved.\"\"\"" in diffs["app.py"]

        # Export improved ZIP and verify
        improved_zip = ws.export_improved_zip()
        with zipfile.ZipFile(io.BytesIO(improved_zip), "r") as zf:
            names = zf.namelist()
            assert "app.py" in names
            updated_code = zf.read("app.py").decode("utf-8")
            assert "Improved" in updated_code
