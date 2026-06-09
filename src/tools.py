from __future__ import annotations

import difflib
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd
from langchain.tools import tool

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.code_analyzer import analyze_python_files, read_file_content, scan_directory
from src.config import LOGGER
from src.parsers import LogParser
from src.rag_engine import StandardKnowledgeBase

_kb: StandardKnowledgeBase | None = None
_log_parser: LogParser | None = None


def _get_kb() -> StandardKnowledgeBase:
    global _kb
    if _kb is None:
        _kb = StandardKnowledgeBase()
    return _kb


def _get_log_parser() -> LogParser:
    global _log_parser
    if _log_parser is None:
        _log_parser = LogParser()
    return _log_parser


# ═══════════════════════════════════════════════════════════
# 探索类工具
# ═══════════════════════════════════════════════════════════

@tool
def scan_codebase(source_dir: str = "data/source_code") -> str:
    """扫描 DMS 源码目录，返回所有 .py 文件的目录树和文件大小。
    这是探索代码的第一步，了解有哪些文件后再用 analyze_code_structure 深入。
    参数: source_dir - 源码目录路径，默认为 data/source_code
    """
    path = ROOT_DIR / source_dir if not Path(source_dir).is_absolute() else Path(source_dir)
    return scan_directory(path)


@tool
def analyze_code_structure(source_dir: str = "data/source_code") -> str:
    """用 AST 解析所有 Python 源码文件，提取类名、方法名、函数、导入依赖、关键常量。
    不读取实现细节，只提取结构骨架。适合在了解文件列表后快速定位关键模块。
    参数: source_dir - 源码目录路径，默认为 data/source_code
    """
    path = ROOT_DIR / source_dir if not Path(source_dir).is_absolute() else Path(source_dir)
    return analyze_python_files(path)


@tool
def read_code_file(file_path: str, start_line: int = 1, end_line: Optional[int] = None) -> str:
    """读取指定 Python 文件的代码内容，可指定行范围。
    先用 analyze_code_structure 定位关键文件，再用本工具精读。
    参数:
      file_path - 文件路径（相对源码目录或绝对路径）
      start_line - 起始行号（从1开始）
      end_line - 结束行号（默认读到文件末尾）
    """
    return read_file_content(file_path, start_line, end_line)


@tool
def parse_performance_logs(log_path: str) -> str:
    """解析 DMS 系统的性能日志 CSV 文件，返回 FPS、延迟、CPU、内存的统计指标。
    包含平均值、最大值、最小值。这是评估系统实时性的第一步。
    参数: log_path - CSV 日志文件路径
    """
    log_path_obj = Path(log_path)
    if not log_path_obj.is_absolute():
        log_path_obj = ROOT_DIR / log_path_obj

    if not log_path_obj.exists():
        return f"日志文件不存在: {log_path_obj}"

    try:
        df = pd.read_csv(log_path_obj)
    except Exception as e:
        return f"读取 CSV 失败: {e}"

    required = {"timestamp", "fps", "latency_ms"}
    missing = required - set(df.columns)
    if missing:
        return f"CSV 缺少必要列: {missing}。现有列: {list(df.columns)}"

    parser = _get_log_parser()
    items = list(parser._rows_to_models(df))
    if not items:
        return "未能从日志中解析出任何有效数据。"

    fps_vals = [x.fps for x in items]
    lat_vals = [x.latency_ms for x in items]
    cpu_vals = [x.cpu_usage for x in items if x.cpu_usage > 0]
    mem_vals = [x.memory_usage_mb for x in items if x.memory_usage_mb > 0]

    def _stats(vals: list[float]) -> dict:
        if not vals:
            return {"avg": "N/A", "max": "N/A", "min": "N/A"}
        return {
            "avg": round(sum(vals) / len(vals), 2),
            "max": round(max(vals), 2),
            "min": round(min(vals), 2),
        }

    result = {
        "样本数": len(items),
        "FPS": _stats(fps_vals),
        "延迟(ms)": _stats(lat_vals),
        "CPU(%)": _stats(cpu_vals) if cpu_vals else "无数据",
        "内存(MB)": _stats(mem_vals) if mem_vals else "无数据",
    }

    # DMS 专用判定
    judgments = []
    avg_fps = result["FPS"]["avg"] if isinstance(result["FPS"], dict) else None
    avg_lat = result["延迟(ms)"]["avg"] if isinstance(result["延迟(ms)"], dict) else None

    if avg_fps is not None:
        if avg_fps >= 30:
            judgments.append("FPS 优秀 (≥30)")
        elif avg_fps >= 15:
            judgments.append("FPS 合格 (≥15)")
        else:
            judgments.append("⚠ FPS 不合格 (<15)，存在严重实时性问题")

    if avg_lat is not None:
        if avg_lat <= 200:
            judgments.append("延迟合格 (≤200ms)")
        elif avg_lat <= 500:
            judgments.append("⚠ 延迟偏高 (200-500ms)，需优化")
        else:
            judgments.append("⛔ 延迟严重超标 (>500ms)，系统不可用")

    output = json.dumps(result, ensure_ascii=False, indent=2)
    if judgments:
        output += "\n\n【DMS 实时性判定】\n" + "\n".join(judgments)
    return output


@tool
def search_standards(query: str) -> str:
    """从国标 GB/T 知识库中检索与 DMS 相关的条款。
    用于检查当前系统是否符合国标要求（如实时性、告警延迟、功能覆盖率等）。
    参数: query - 搜索关键词，如 "报警延迟 要求" 或 "疲劳检测 时间窗"
    """
    kb = _get_kb()
    results = kb.search_standard(query, k=3)
    if not results:
        return "未找到相关国标条款。请尝试换一个搜索关键词。"
    return results


@tool
def search_web(query: str) -> str:
    """搜索互联网获取 DMS 相关的技术资料和优化方案。
    适用于：查找模型轻量化方案、性能优化技巧、开源实现参考等。
    参数: query - 搜索问题，如 "RetinaFace MobileNet 替代方案 实时人脸检测"
    """
    try:
        from duckduckgo_search import DDGS
    except ImportError:
        return "duckduckgo-search 未安装。请运行: pip install duckduckgo-search"

    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=5))
        if not results:
            return f"未找到关于 '{query}' 的搜索结果。"
        lines = [f"搜索: {query}\n"]
        for i, r in enumerate(results, 1):
            lines.append(f"{i}. **{r.get('title', '无标题')}**")
            lines.append(f"   {r.get('body', '')[:200]}")
            lines.append(f"   🔗 {r.get('href', '')}")
            lines.append("")
        return "\n".join(lines)
    except Exception as e:
        return f"搜索失败: {e}"


# ═══════════════════════════════════════════════════════════
# 行动类工具
# ═══════════════════════════════════════════════════════════

@tool
def modify_code(file_path: str, old_snippet: str, new_snippet: str) -> str:
    """⚠ 修改 DMS 系统源码。使用前必须确认:
    1. 已理解修改的影响范围
    2. 不删除安全相关逻辑
    3. 不降低告警灵敏度
    4. 修改原因关联到具体指标或国标条款

    参数:
      file_path - 要修改的文件路径
      old_snippet - 原代码片段（需精准匹配）
      new_snippet - 新代码片段
    """
    path = Path(file_path)
    if not path.is_absolute():
        alt = ROOT_DIR / "data" / "source_code" / file_path
        if alt.exists():
            path = alt
        else:
            path = ROOT_DIR / file_path

    if not path.exists():
        return f"❌ 文件不存在: {path}\n请先用 scan_codebase 确认文件路径。"

    try:
        original = path.read_text(encoding="utf-8")
    except Exception as e:
        return f"❌ 读取文件失败: {e}"

    count = original.count(old_snippet)
    if count == 0:
        return f"❌ 在 {path.name} 中未找到要替换的代码片段。\n请用 read_code_file 确认准确内容。"

    if count > 1:
        return (
            f"⚠ 找到 {count} 处匹配，请提供更精确的上下文以确保只修改目标位置。\n"
            f"用 read_code_file 查看完整内容后选择更长的唯一片段。"
        )

    modified = original.replace(old_snippet, new_snippet, 1)

    # 安全检查
    safety_keywords = ["alert", "warn", "safety", "critical", "emergency"]
    is_safety_related = any(k in old_snippet.lower() for k in safety_keywords)
    risk = "⚠ 高风险" if is_safety_related else "✅ 低风险"

    # 生成 diff
    diff = difflib.unified_diff(
        original.splitlines(keepends=True),
        modified.splitlines(keepends=True),
        fromfile=str(path),
        tofile=str(path),
    )
    diff_text = "".join(diff)

    # 实际写入
    try:
        path.write_text(modified, encoding="utf-8")
    except Exception as e:
        return f"❌ 写入文件失败: {e}"

    return (
        f"✅ 已修改 {path.name}\n"
        f"风险评估: {risk}\n\n"
        f"```diff\n{diff_text}\n```\n"
        f"💡 建议: 修改后请在实际 DMS 系统上验证相关指标是否改善。"
    )


@tool
def compare_metrics(old_log: str, new_log: str) -> str:
    """对比优化前后的两份性能日志，分析各项指标的变化。
    参数:
      old_log - 优化前的 CSV 日志路径
      new_log - 优化后的 CSV 日志路径
    """
    def _read_csv(p: str) -> pd.DataFrame | None:
        path = Path(p)
        if not path.is_absolute():
            path = ROOT_DIR / path
        if not path.exists():
            return None
        try:
            return pd.read_csv(path)
        except Exception:
            return None

    df_old = _read_csv(old_log)
    df_new = _read_csv(new_log)

    if df_old is None:
        return f"旧日志文件不存在或无法读取: {old_log}"
    if df_new is None:
        return f"新日志文件不存在或无法读取: {new_log}"

    parser = _get_log_parser()

    def _avg(items, field):
        vals = [getattr(x, field) for x in items if getattr(x, field, 0) > 0]
        return round(sum(vals) / len(vals), 2) if vals else None

    old_items = list(parser._rows_to_models(df_old))
    new_items = list(parser._rows_to_models(df_new))

    metrics = ["fps", "latency_ms", "cpu_usage", "memory_usage_mb"]
    labels = {"fps": "FPS ↑", "latency_ms": "延迟(ms) ↓", "cpu_usage": "CPU(%) ↓", "memory_usage_mb": "内存(MB) ↓"}

    lines = ["## 优化前后对比\n", f"| 指标 | 优化前 | 优化后 | 变化 | 判定 |", "|------|--------|--------|------|------|"]

    for m in metrics:
        old_val = _avg(old_items, m)
        new_val = _avg(new_items, m)
        if old_val is None or new_val is None:
            continue
        change = round(new_val - old_val, 2)
        pct = round((change / old_val) * 100, 1) if old_val != 0 else 0

        if m == "fps":
            good = change > 0
        else:
            good = change < 0

        if abs(pct) < 5:
            verdict = "➡ 基本持平"
        elif good:
            verdict = "✅ 改善" if abs(pct) < 30 else "✅ 显著改善"
        else:
            verdict = "⚠ 恶化" if abs(pct) < 30 else "⛔ 严重恶化"

        lines.append(f"| {labels[m]} | {old_val} | {new_val} | {change:+} ({pct:+}%) | {verdict} |")

    return "\n".join(lines)


@tool
def save_report(report_content: str) -> str:
    """将最终的评估报告保存到 reports/ 目录。
    参数: report_content - 完整的 Markdown 格式评估报告内容
    """
    reports_dir = ROOT_DIR / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = reports_dir / f"dms_report_{timestamp}.md"
    try:
        report_path.write_text(report_content, encoding="utf-8")
        return f"✅ 报告已保存到: {report_path}"
    except Exception as e:
        return f"❌ 保存报告失败: {e}"
