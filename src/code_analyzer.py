"""AST-based Python code structure analyzer for DMS source code exploration."""

from __future__ import annotations

import ast
from pathlib import Path
def scan_directory(root: str | Path) -> str:
    """扫描目录结构，返回文件树和大小。只关注 .py 文件。"""
    root = Path(root)
    if not root.exists():
        return f"目录不存在: {root}"

    lines: list[str] = [f"[DIR] {root.name}/"]
    py_files = sorted(root.rglob("*.py"))
    if not py_files:
        return "未找到任何 .py 文件。"

    # 构建目录树
    dirs: dict[str, list[tuple[str, int]]] = {}
    for f in py_files:
        try:
            size_kb = f.stat().st_size / 1024
        except OSError:
            size_kb = 0
        rel = f.relative_to(root)
        parent = str(rel.parent) if str(rel.parent) != "." else ""
        dirs.setdefault(parent, []).append((rel.name, round(size_kb, 1)))

    for parent, files in sorted(dirs.items()):
        prefix = f"  {parent}/" if parent else ""
        for name, size in files:
            indent = "    " if parent else "  "
            lines.append(f"{indent}{prefix}{name} ({size} KB)")

    lines.append(f"\n共 {len(py_files)} 个 .py 文件")
    return "\n".join(lines)


def analyze_python_files(root: str | Path) -> str:
    """用 AST 解析所有 .py 文件，提取结构骨架。"""
    root = Path(root)
    if not root.exists():
        return f"目录不存在: {root}"

    py_files = sorted(root.rglob("*.py"))
    if not py_files:
        return "未找到任何 .py 文件。"

    output: list[str] = []
    for f in py_files:
        try:
            source = f.read_text(encoding="utf-8")
        except Exception:
            continue

        rel_path = f.relative_to(root)
        size_kb = round(f.stat().st_size / 1024, 1)

        try:
            tree = ast.parse(source)
        except SyntaxError:
            output.append(f"### {rel_path} ({size_kb} KB) [SYNTAX ERROR]")
            continue

        info = _extract_structure(tree, source)
        if not info["classes"] and not info["functions"] and not info["imports"] and not info["constants"]:
            continue

        output.append(f"### {rel_path} ({size_kb} KB)")

        if info["doc"]:
            output.append(f"> {info['doc'][:120]}")

        if info["imports"]:
            deps = _summarize_imports(info["imports"])
            output.append(f"依赖: {deps}")

        for cls in info["classes"]:
            methods = ", ".join(cls["methods"][:8])
            more = "..." if len(cls["methods"]) > 8 else ""
            output.append(f"class {cls['name']}({', '.join(cls['bases'])}) — {methods}{more}")

        if info["functions"]:
            fns = ", ".join(info["functions"][:10])
            more = "..." if len(info["functions"]) > 10 else ""
            output.append(f"函数: {fns}{more}")

        if info["constants"]:
            consts = ", ".join(info["constants"][:12])
            output.append(f"关键常量: {consts}")

        output.append("")

    return "\n".join(output).strip()


def read_file_content(path: str | Path, start: int = 1, end: int | None = None) -> str:
    """读取指定文件的指定行范围。"""
    path = Path(path)
    if not path.exists():
        return f"文件不存在: {path}"

    try:
        lines_list = path.read_text(encoding="utf-8").splitlines()
    except Exception as e:
        return f"读取失败: {e}"

    total = len(lines_list)
    if end is None:
        end = total
    start = max(1, start)
    end = min(end, total)

    result: list[str] = [f"# {path} (行 {start}-{end} / 共 {total} 行)\n"]
    for i in range(start - 1, end):
        result.append(f"{i + 1:4d}| {lines_list[i]}")

    if end < total:
        result.append(f"\n... 还有 {total - end} 行未显示，使用更大的 end 值继续读取")

    return "\n".join(result)


def _extract_structure(tree: ast.AST, source: str) -> dict:
    """从 AST 中提取类、函数、导入、常量。"""
    result: dict = {
        "doc": ast.get_docstring(tree),
        "classes": [],
        "functions": [],
        "imports": [],
        "constants": [],
    }

    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.ClassDef):
            methods = [
                m.name for m in node.body
                if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef))
            ]
            bases = [_base_name(b) for b in node.bases]
            result["classes"].append({
                "name": node.name,
                "bases": bases,
                "methods": methods,
            })
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if not node.name.startswith("_"):
                result["functions"].append(node.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                result["imports"].append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                result["imports"].append(node.module)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id.isupper():
                    result["constants"].append(target.id)

    return result


def _base_name(node: ast.expr) -> str:
    """提取基类名称。"""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return "?"


def _summarize_imports(imports: list[str]) -> str:
    """归纳导入模块，提取高频关键词。"""
    key_modules = {"torch", "tensorflow", "cv2", "numpy", "dlib", "threading",
                   "multiprocessing", "yolo", "mtcnn", "retinaface", "shufflenet",
                   "mobilenet", "resnet", "onnx", "tensorrt"}
    found = [m for m in imports if any(k in m.lower() for k in key_modules)]
    if not found:
        top = imports[:4]
        more = f" +{len(imports) - 4}个" if len(imports) > 4 else ""
        return ", ".join(top) + more
    return ", ".join(found[:6])


