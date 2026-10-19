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
        "docstring_count": 0,
        "typed_function_count": 0,
        "lines_of_code": len([line for line in code.splitlines() if line.strip() and not line.strip().startswith("#")]),
        "cyclomatic_complexity": 1,
        "security_flags": [],
        "security_score": 100,
    }
    
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        err_msg = f"SyntaxError at line {e.lineno}, col {e.offset}: {e.msg}"
        return False, err_msg, metadata
    except Exception as e:
        return False, str(e), metadata
        
    for node in ast.walk(tree):
        # Functions & Type Hint Metrics
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            metadata["num_functions"] += 1
            if ast.get_docstring(node):
                metadata["has_docstrings"] = True
                metadata["docstring_count"] += 1
            if node.returns is not None or any(arg.annotation is not None for arg in node.args.args):
                metadata["typed_function_count"] += 1

        # Classes
        elif isinstance(node, ast.ClassDef):
            metadata["num_classes"] += 1
            if ast.get_docstring(node):
                metadata["has_docstrings"] = True
                metadata["docstring_count"] += 1

        # Complexity branches
        elif isinstance(node, (ast.If, ast.For, ast.While, ast.ExceptHandler, ast.With)):
            metadata["cyclomatic_complexity"] += 1

        # Imports
        elif isinstance(node, ast.Import):
            for alias in node.names:
                metadata["imports"].append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                metadata["imports"].append(node.module)

        # Static Security Pattern Detection
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                if node.func.id in ("eval", "exec"):
                    metadata["security_flags"].append(f"Dangerous built-in: {node.func.id}() used at line {getattr(node, 'lineno', '?')}")
                    metadata["security_score"] = max(0, metadata["security_score"] - 35)
                elif node.func.id == "input" and "subprocess" in metadata["imports"]:
                    metadata["security_flags"].append("Potential command injection vector")
                    metadata["security_score"] = max(0, metadata["security_score"] - 20)

    return True, None, metadata
