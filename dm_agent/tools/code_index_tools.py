"""Lightweight code indexing tools for repository-level Python understanding."""

from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set

from .base import _require_str

DEFAULT_INDEX_EXCLUDES = {
    ".git",
    ".hg",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
    "site-packages",
}


def build_code_index(arguments: Dict[str, Any]) -> str:
    """Build a lightweight Python symbol index for a repository tree."""
    root = Path(arguments.get("root", ".")).resolve()
    max_files = int(arguments.get("max_files", 200))
    include_tests = bool(arguments.get("include_tests", True))

    if not root.exists():
        return f"Directory {root} does not exist."
    if not root.is_dir():
        return f"Path {root} is not a directory."

    files = []
    symbol_count = 0
    parse_errors = []
    for path in _iter_python_files(root, max_files=max_files, include_tests=include_tests):
        relative = path.relative_to(root).as_posix()
        try:
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(path))
        except SyntaxError as exc:
            parse_errors.append({"path": relative, "error": str(exc)})
            continue

        module = _module_name(root, path)
        symbols = _index_symbols(tree, relative, module)
        symbol_count += len(symbols)
        files.append(
            {
                "path": relative,
                "module": module,
                "imports": _index_imports(tree, module),
                "symbols": symbols,
            }
        )

    result = {
        "root": str(root),
        "file_count": len(files),
        "symbol_count": symbol_count,
        "files": files,
        "parse_errors": parse_errors,
    }
    return json.dumps(result, indent=2, ensure_ascii=False)


def search_symbol(arguments: Dict[str, Any]) -> str:
    """Search Python symbols by exact name or substring in a repository tree."""
    name = _require_str(arguments, "name")
    root = Path(arguments.get("root", ".")).resolve()
    kind = arguments.get("kind")
    exact = bool(arguments.get("exact", False))
    max_files = int(arguments.get("max_files", 200))

    if kind is not None and kind not in {"class", "function", "method"}:
        raise ValueError("kind must be one of: class, function, method")

    index = json.loads(
        build_code_index(
            {
                "root": str(root),
                "max_files": max_files,
                "include_tests": arguments.get("include_tests", True),
            }
        )
    )
    matches = []
    for file_info in index.get("files", []):
        for symbol in file_info.get("symbols", []):
            if kind and symbol.get("kind") != kind:
                continue
            symbol_name = symbol.get("name", "")
            qualified_name = symbol.get("qualified_name", "")
            if exact:
                matched = name in {symbol_name, qualified_name}
            else:
                needle = name.lower()
                matched = needle in symbol_name.lower() or needle in qualified_name.lower()
            if matched:
                matches.append(symbol)

    result = {
        "root": str(root),
        "query": name,
        "kind": kind,
        "exact": exact,
        "match_count": len(matches),
        "matches": matches,
    }
    return json.dumps(result, indent=2, ensure_ascii=False)


def dependency_graph(arguments: Dict[str, Any]) -> str:
    """Build a local Python import dependency graph for a repository tree."""
    root = Path(arguments.get("root", ".")).resolve()
    max_files = int(arguments.get("max_files", 200))
    include_external = bool(arguments.get("include_external", False))

    if not root.exists():
        return f"Directory {root} does not exist."
    if not root.is_dir():
        return f"Path {root} is not a directory."

    paths = list(_iter_python_files(root, max_files=max_files, include_tests=True))
    module_to_path = {_module_name(root, path): path.relative_to(root).as_posix() for path in paths}
    nodes = [{"id": module, "path": path} for module, path in sorted(module_to_path.items())]
    edges = []
    external: Set[str] = set()

    for path in paths:
        module = _module_name(root, path)
        try:
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(path))
        except SyntaxError:
            continue
        for imported in _imported_modules(tree, module):
            target = _match_local_module(imported, module_to_path)
            if target:
                edges.append({"from": module, "to": target, "import": imported})
            elif include_external:
                external.add(imported)

    result = {
        "root": str(root),
        "nodes": nodes,
        "edges": sorted(edges, key=lambda edge: (edge["from"], edge["to"], edge["import"])),
        "external_modules": sorted(external),
    }
    return json.dumps(result, indent=2, ensure_ascii=False)


def _iter_python_files(root: Path, *, max_files: int, include_tests: bool) -> Iterable[Path]:
    count = 0
    for path in sorted(root.rglob("*.py")):
        relative_parts = path.relative_to(root).parts
        if any(part in DEFAULT_INDEX_EXCLUDES for part in relative_parts):
            continue
        if not include_tests and any(part in {"test", "tests"} for part in relative_parts):
            continue
        yield path
        count += 1
        if count >= max_files:
            break


def _module_name(root: Path, path: Path) -> str:
    relative = path.relative_to(root).with_suffix("")
    parts = list(relative.parts)
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _index_symbols(tree: ast.AST, path: str, module: str) -> List[Dict[str, Any]]:
    symbols: List[Dict[str, Any]] = []
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            class_symbol = _symbol_payload(node, "class", path, module, node.name)
            class_symbol["methods"] = []
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    qualified_name = f"{node.name}.{item.name}"
                    method_symbol = _symbol_payload(item, "method", path, module, qualified_name)
                    class_symbol["methods"].append(method_symbol)
                    symbols.append(method_symbol)
            symbols.append(class_symbol)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            symbols.append(_symbol_payload(node, "function", path, module, node.name))
    return sorted(symbols, key=lambda item: (item["path"], item["line"], item["qualified_name"]))


def _symbol_payload(
    node: ast.AST,
    kind: str,
    path: str,
    module: str,
    qualified_name: str,
) -> Dict[str, Any]:
    name = qualified_name.split(".")[-1]
    payload = {
        "name": name,
        "qualified_name": f"{module}.{qualified_name}" if module else qualified_name,
        "kind": kind,
        "path": path,
        "line": getattr(node, "lineno", None),
        "end_line": getattr(node, "end_lineno", None),
        "docstring": None,
    }
    if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
        payload["docstring"] = ast.get_docstring(node)
    return payload


def _index_imports(tree: ast.AST, module: str) -> List[Dict[str, Any]]:
    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append({"module": alias.name, "name": None, "line": node.lineno})
        elif isinstance(node, ast.ImportFrom):
            names = [alias.name for alias in node.names]
            resolved_modules = _resolve_import_from_names(module, node.level, node.module, names)
            for alias, resolved in zip(node.names, resolved_modules):
                imports.append(
                    {
                        "module": resolved,
                        "name": alias.name,
                        "line": node.lineno,
                    }
                )
    return imports


def _imported_modules(tree: ast.AST, module: str) -> Set[str]:
    modules: Set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            names = [alias.name for alias in node.names]
            modules.update(_resolve_import_from_names(module, node.level, node.module, names))
    return {item for item in modules if item}


def _resolve_import_from(current_module: str, level: int, module: Optional[str]) -> str:
    if level <= 0:
        return module or ""

    parts = current_module.split(".") if current_module else []
    base = parts[: max(len(parts) - level, 0)]
    if module:
        base.extend(module.split("."))
    return ".".join(part for part in base if part)


def _resolve_import_from_names(
    current_module: str,
    level: int,
    module: Optional[str],
    names: List[str],
) -> List[str]:
    base = _resolve_import_from(current_module, level, module)
    if level > 0 and not module:
        return [f"{base}.{name}" if base else name for name in names if name != "*"]
    return [base for _ in names]


def _match_local_module(imported: str, module_to_path: Dict[str, str]) -> Optional[str]:
    if imported in module_to_path:
        return imported
    parts = imported.split(".")
    while len(parts) > 1:
        parts.pop()
        candidate = ".".join(parts)
        if candidate in module_to_path:
            return candidate
    return None
