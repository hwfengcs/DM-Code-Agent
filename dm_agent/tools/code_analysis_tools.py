"""代码分析工具 - 提供代码结构理解能力"""

from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any, Dict, List

from .base import _require_str


def parse_ast(arguments: Dict[str, Any]) -> str:
    """
    解析 Python 文件的 AST，提取函数、类、导入等结构信息

    Args:
        arguments: {"path": "文件路径"}

    Returns:
        JSON 格式的代码结构信息
    """
    path_value = _require_str(arguments, "path")
    path = Path(path_value)

    if not path.exists():
        return f"文件 {path} 不存在。"
    if not path.is_file():
        return f"路径 {path} 不是文件。"
    if path.suffix != ".py":
        return f"文件 {path} 不是 Python 文件。"

    try:
        with open(path, "r", encoding="utf-8") as f:
            source_code = f.read()

        tree = ast.parse(source_code, filename=str(path))

        # 提取信息
        analysis = {
            "file": str(path),
            "imports": _extract_imports(tree),
            "classes": _extract_classes(tree),
            "functions": _extract_functions(tree),
            "global_variables": _extract_global_variables(tree),
        }

        return json.dumps(analysis, indent=2, ensure_ascii=False)

    except SyntaxError as e:
        return f"Python 语法错误：{e}"
    except Exception as e:
        return f"解析失败：{e}"


def _extract_imports(tree: ast.AST) -> List[Dict[str, Any]]:
    """提取导入语句"""
    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(
                    {
                        "type": "import",
                        "module": alias.name,
                        "alias": alias.asname,
                        "line": node.lineno,
                    }
                )
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                imports.append(
                    {
                        "type": "from_import",
                        "module": node.module or "",
                        "name": alias.name,
                        "alias": alias.asname,
                        "line": node.lineno,
                    }
                )
    return imports


def _extract_classes(tree: ast.AST) -> List[Dict[str, Any]]:
    """提取类定义"""
    classes = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            # 提取基类
            bases = [_get_name(base) for base in node.bases]

            # 提取方法
            methods = []
            for item in node.body:
                if isinstance(item, ast.FunctionDef):
                    methods.append(
                        {
                            "name": item.name,
                            "line": item.lineno,
                            "args": [arg.arg for arg in item.args.args],
                            "is_async": isinstance(item, ast.AsyncFunctionDef),
                        }
                    )

            classes.append(
                {
                    "name": node.name,
                    "line": node.lineno,
                    "bases": bases,
                    "methods": methods,
                    "decorators": [_get_name(d) for d in node.decorator_list],
                }
            )
    return classes


def _extract_functions(tree: ast.AST) -> List[Dict[str, Any]]:
    """提取顶层函数定义"""
    functions = []
    for node in tree.body:  # 只提取顶层函数
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            # 提取参数信息
            args_info = []
            for arg in node.args.args:
                arg_dict = {"name": arg.arg}
                if arg.annotation:
                    arg_dict["annotation"] = _get_name(arg.annotation)
                args_info.append(arg_dict)

            # 提取返回值类型
            return_type = None
            if node.returns:
                return_type = _get_name(node.returns)

            functions.append(
                {
                    "name": node.name,
                    "line": node.lineno,
                    "args": args_info,
                    "return_type": return_type,
                    "is_async": isinstance(node, ast.AsyncFunctionDef),
                    "decorators": [_get_name(d) for d in node.decorator_list],
                    "docstring": ast.get_docstring(node),
                }
            )
    return functions


def _extract_global_variables(tree: ast.AST) -> List[Dict[str, Any]]:
    """提取全局变量"""
    variables = []
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    variables.append(
                        {
                            "name": target.id,
                            "line": node.lineno,
                            "type": type(node.value).__name__,
                        }
                    )
    return variables


def _get_name(node: ast.AST) -> str:
    """从 AST 节点获取名称"""
    if isinstance(node, ast.Name):
        return node.id
    elif isinstance(node, ast.Attribute):
        value = _get_name(node.value)
        return f"{value}.{node.attr}"
    elif isinstance(node, ast.Constant):
        return str(node.value)
    elif isinstance(node, ast.Subscript):
        value = _get_name(node.value)
        slice_value = _get_name(node.slice)
        return f"{value}[{slice_value}]"
    else:
        return ast.unparse(node) if hasattr(ast, "unparse") else "<unknown>"


def get_function_signature(arguments: Dict[str, Any]) -> str:
    """
    提取指定函数的完整签名

    Args:
        arguments: {"path": "文件路径", "function_name": "函数名"}

    Returns:
        函数签名信息
    """
    path_value = _require_str(arguments, "path")
    function_name = _require_str(arguments, "function_name")

    path = Path(path_value)
    if not path.exists():
        return f"文件 {path} 不存在。"
    if not path.is_file():
        return f"路径 {path} 不是文件。"

    try:
        with open(path, "r", encoding="utf-8") as f:
            source_code = f.read()

        tree = ast.parse(source_code, filename=str(path))

        # 查找函数
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name == function_name:
                    # 构建签名
                    args_str = []
                    for arg in node.args.args:
                        arg_str = arg.arg
                        if arg.annotation:
                            arg_str += f": {_get_name(arg.annotation)}"
                        args_str.append(arg_str)

                    signature = f"def {node.name}({', '.join(args_str)})"
                    if node.returns:
                        signature += f" -> {_get_name(node.returns)}"

                    result = {
                        "signature": signature,
                        "line": node.lineno,
                        "docstring": ast.get_docstring(node),
                        "is_async": isinstance(node, ast.AsyncFunctionDef),
                    }

                    return json.dumps(result, indent=2, ensure_ascii=False)

        return f"未找到函数 '{function_name}'。"

    except Exception as e:
        return f"提取函数签名失败：{e}"


def find_dependencies(arguments: Dict[str, Any]) -> str:
    """
    分析文件的依赖关系

    Args:
        arguments: {"path": "文件路径"}

    Returns:
        依赖关系信息
    """
    path_value = _require_str(arguments, "path")
    path = Path(path_value)

    if not path.exists():
        return f"文件 {path} 不存在。"
    if not path.is_file():
        return f"路径 {path} 不是文件。"

    try:
        with open(path, "r", encoding="utf-8") as f:
            source_code = f.read()

        tree = ast.parse(source_code, filename=str(path))

        # 提取所有导入
        imports = _extract_imports(tree)

        # 分类：标准库、第三方库、本地模块
        stdlib_modules = set()
        third_party_modules = set()
        local_modules = set()

        import sys
        stdlib_module_names = set(sys.stdlib_module_names)

        for imp in imports:
            module = imp.get("module", "")
            if not module:
                continue

            # 获取顶层模块名
            top_module = module.split(".")[0]

            if top_module in stdlib_module_names:
                stdlib_modules.add(module)
            elif top_module.startswith("."):
                local_modules.add(module)
            else:
                # 简单判断：如果路径中存在对应文件夹，认为是本地模块
                parent_path = path.parent / top_module
                if parent_path.exists():
                    local_modules.add(module)
                else:
                    third_party_modules.add(module)

        result = {
            "file": str(path),
            "standard_library": sorted(list(stdlib_modules)),
            "third_party": sorted(list(third_party_modules)),
            "local_modules": sorted(list(local_modules)),
            "total_imports": len(imports),
        }

        return json.dumps(result, indent=2, ensure_ascii=False)

    except Exception as e:
        return f"分析依赖关系失败：{e}"


def get_code_metrics(arguments: Dict[str, Any]) -> str:
    """
    获取代码度量信息（行数、复杂度等）

    Args:
        arguments: {"path": "文件路径"}

    Returns:
        代码度量信息
    """
    path_value = _require_str(arguments, "path")
    path = Path(path_value)

    if not path.exists():
        return f"文件 {path} 不存在。"
    if not path.is_file():
        return f"路径 {path} 不是文件。"

    try:
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        # 统计行数
        total_lines = len(lines)
        code_lines = 0
        comment_lines = 0
        blank_lines = 0

        for line in lines:
            stripped = line.strip()
            if not stripped:
                blank_lines += 1
            elif stripped.startswith("#"):
                comment_lines += 1
            else:
                code_lines += 1

        # 如果是 Python 文件，提取更多信息
        metrics = {
            "file": str(path),
            "total_lines": total_lines,
            "code_lines": code_lines,
            "comment_lines": comment_lines,
            "blank_lines": blank_lines,
        }

        if path.suffix == ".py":
            try:
                with open(path, "r", encoding="utf-8") as f:
                    source = f.read()
                tree = ast.parse(source)

                # 统计函数和类数量
                num_functions = sum(
                    1
                    for node in ast.walk(tree)
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                )
                num_classes = sum(
                    1 for node in ast.walk(tree) if isinstance(node, ast.ClassDef)
                )

                metrics["num_functions"] = num_functions
                metrics["num_classes"] = num_classes
            except:
                pass

        return json.dumps(metrics, indent=2, ensure_ascii=False)

    except Exception as e:
        return f"获取代码度量失败：{e}"