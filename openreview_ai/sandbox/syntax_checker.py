import ast
from typing import Dict, Any, Optional, Tuple


def check_syntax(code: str, language: str = "python") -> Tuple[bool, Optional[str], Dict[str, Any]]:
    """
    Validates code syntax and extracts structural metadata.
    Returns: (is_valid, error_message, metadata)
    """
    if language.lower() != "python":
        # For non-python languages, basic brace check
        return True, None, {"language": language}
    
    metadata: Dict[str, Any] = {
        "num_functions": 0,
        "num_classes": 0,
        "imports": [],
        "has_docstrings": False,
    }
    
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        err_msg = f"SyntaxError at line {e.lineno}, col {e.offset}: {e.msg}"
        return False, err_msg, metadata
    except Exception as e:
        return False, str(e), metadata
        
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            metadata["num_functions"] += 1
            if ast.get_docstring(node):
                metadata["has_docstrings"] = True
        elif isinstance(node, ast.ClassDef):
            metadata["num_classes"] += 1
            if ast.get_docstring(node):
                metadata["has_docstrings"] = True
        elif isinstance(node, ast.Import):
            for alias in node.names:
                metadata["imports"].append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                metadata["imports"].append(node.module)
                
    return True, None, metadata
