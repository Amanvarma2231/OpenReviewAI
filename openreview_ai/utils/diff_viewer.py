import difflib
from typing import List, Tuple


def compute_unified_diff(old_code: str, new_code: str, from_title: str = "Original Code", to_title: str = "Revised Code") -> str:
    """Computes a standard unified diff string between two code versions."""
    old_lines = old_code.splitlines(keepends=True)
    new_lines = new_code.splitlines(keepends=True)
    
    diff = difflib.unified_diff(
        old_lines,
        new_lines,
        fromfile=from_title,
        tofile=to_title,
        lineterm=""
    )
    return "".join(diff)


def compute_line_changes(old_code: str, new_code: str) -> List[Tuple[str, str]]:
    """
    Returns list of (change_type, line_content).
    change_type can be: '+', '-', ' '
    """
    old_lines = old_code.splitlines()
    new_lines = new_code.splitlines()
    
    matcher = difflib.SequenceMatcher(None, old_lines, new_lines)
    changes = []
    
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == 'equal':
            for line in old_lines[i1:i2]:
                changes.append((' ', line))
        elif tag == 'delete':
            for line in old_lines[i1:i2]:
                changes.append(('-', line))
        elif tag == 'insert':
            for line in new_lines[j1:j2]:
                changes.append(('+', line))
        elif tag == 'replace':
            for line in old_lines[i1:i2]:
                changes.append(('-', line))
            for line in new_lines[j1:j2]:
                changes.append(('+', line))
                
    return changes
