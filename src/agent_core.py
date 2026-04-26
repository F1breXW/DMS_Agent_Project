from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from typing import Callable, Iterable, Optional

import pandas as pd
from langchain_openai import ChatOpenAI

# 运行脚本时把项目根目录加入 sys.path，确保可以导入 src.*
ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.config import (
    DEEPSEEK_API_BASE,
    DEEPSEEK_API_KEY,
    DMS_LLM_MODEL,
    DMS_MAX_TOKENS,
    DMS_TEMPERATURE,
    DMS_TOP_P,
    LOGGER,
)
from src.parsers import CodeParser, LogParseResult, LogParser
from src.rag_engine import StandardKnowledgeBase


class DMSDigitalEngineer:
    """整合日志解析、标准检索与 LLM 推理的数字工程师。"""

    def __init__(
        self,
        model_name: str | None = None,
        temperature: float | None = None,
        top_p: float | None = None,
        max_tokens: int | None = None,
    ) -> None:
        self.log_parser = LogParser()
        self.code_parser = CodeParser()
        self.knowledge_base = StandardKnowledgeBase()
        self.code_summary = self._load_code_summary(
            ROOT_DIR / "docs" / "dms_prompt_snippet.txt"
        )

        if not DEEPSEEK_API_KEY:
            LOGGER.warning("DEEPSEEK_API_KEY is empty; LLM call may fail.")

        model_name = model_name or DMS_LLM_MODEL
        temperature = DMS_TEMPERATURE if temperature is None else temperature
        top_p = DMS_TOP_P if top_p is None else top_p
        max_tokens = DMS_MAX_TOKENS if max_tokens is None else max_tokens

        self.llm = ChatOpenAI(
            base_url=DEEPSEEK_API_BASE,
            api_key=DEEPSEEK_API_KEY,
            model=model_name,
            temperature=temperature,
            top_p=top_p,
            max_tokens=max_tokens,
        )

    def analyze_and_optimize(
        self,
        log_file: str | Path | list[str | Path],
        code_file: str | Path | list[str | Path],
        status_callback: Callable[[str], None] | None = None,
        save_report: bool = False,
    ) -> str:
        """解析日志与源码，检索国标并调用大模型输出评估报告。"""

        self._update_status(status_callback, "解析日志中...")

        # 先解析日志，获取平均指标
        log_result = self._parse_log_input(log_file)

        self._update_status(status_callback, "解析源码中...")
        # 再解析源码
        code_text = self._read_code_content(code_file)
        code_is_summary = False
        if self.code_summary:
            code_text = self.code_summary
            code_is_summary = True

        self._update_status(status_callback, "检索国标中...")
        # 再根据指标检索国标要求
        standard_query = self._build_standard_query(log_result.avg_latency_ms)
        standard_text = self.knowledge_base.search_standard(standard_query, k=3)

        self._update_status(status_callback, "调用大模型生成报告中...")
        # 最后组合 Prompt 调用大模型
        prompt = self._build_prompt(
            log_result=log_result,
            code_text=code_text,
            standard_text=standard_text,
            code_is_summary=code_is_summary,
        )

        response = self.llm.invoke(prompt)
        report = getattr(response, "content", "")

        if save_report:
            self._save_report(report)

        self._update_status(status_callback, "报告生成完成")
        return report

    def _parse_log_input(self, log_input: str | Path | list[str | Path]) -> LogParseResult:
        """解析单个或多个日志文件/目录并计算平均指标。"""

        paths = self._normalize_paths(log_input)
        log_files = self._collect_files(paths, suffixes={".csv"})
        if not log_files:
            LOGGER.error("No log files found from input: %s", log_input)
            return LogParseResult(items=[], avg_fps=None, avg_latency_ms=None)

        items = []
        for log_path in log_files:
            try:
                df = pd.read_csv(log_path)
                items.extend(self.log_parser._rows_to_models(df))
            except Exception as exc:  # noqa: BLE001
                LOGGER.error("Failed to parse log file %s: %s", log_path, exc)

        if not items:
            return LogParseResult(items=[], avg_fps=None, avg_latency_ms=None)

        avg_fps = sum(x.fps for x in items) / len(items)
        avg_latency_ms = sum(x.latency_ms for x in items) / len(items)
        return LogParseResult(items=items, avg_fps=avg_fps, avg_latency_ms=avg_latency_ms)

    def _read_code_content(self, code_input: str | Path | list[str | Path]) -> str:
        """读取源码内容，支持单文件、多个文件或目录。"""

        paths = self._normalize_paths(code_input)
        code_files = self._collect_files(paths, suffixes={".py"})
        if not code_files:
            LOGGER.error("No code files found from input: %s", code_input)
            return ""

        parts: list[str] = []
        for path in code_files:
            try:
                content = path.read_text(encoding="utf-8")
            except Exception as exc:  # noqa: BLE001
                LOGGER.error("Failed to read code file %s: %s", path, exc)
                continue
            parts.append(f"\n# File: {path}\n{content}")

        return "\n".join(parts).strip()

    def _normalize_paths(
        self, value: str | Path | list[str | Path] | None
    ) -> list[Path]:
        """将输入统一转换为路径列表。"""

        if value is None:
            return []
        if isinstance(value, (str, Path)):
            return [Path(value)]
        return [Path(item) for item in value if item]

    def _collect_files(self, paths: Iterable[Path], suffixes: set[str]) -> list[Path]:
        """从文件/目录列表中收集指定后缀的文件。"""

        results: list[Path] = []
        seen: set[Path] = set()

        for path in paths:
            if path.is_dir():
                for file_path in sorted(path.rglob("*")):
                    if file_path.suffix.lower() in suffixes and file_path not in seen:
                        results.append(file_path)
                        seen.add(file_path)
                continue

            if path.is_file():
                if path.suffix.lower() in suffixes and path not in seen:
                    results.append(path)
                    seen.add(path)
                continue

            LOGGER.warning("Path does not exist: %s", path)

        return results

    def _build_standard_query(self, avg_latency_ms: Optional[float]) -> str:
        """根据平均延迟构造国标检索问题。"""

        if avg_latency_ms is None:
            return "报警延迟 要求"
        if avg_latency_ms > 1000:
            return "报警延迟 超时 要求"
        return "报警响应 时间 要求"

    def _build_prompt(
        self,
        log_result: LogParseResult,
        code_text: str,
        standard_text: str,
        code_is_summary: bool,
    ) -> str:
        """组合评估提示词。"""

        avg_fps_text = (
            f"{log_result.avg_fps:.2f}" if log_result.avg_fps is not None else "未知"
        )
        avg_latency_text = (
            f"{log_result.avg_latency_ms:.2f} ms"
            if log_result.avg_latency_ms is not None
            else "未知"
        )

        code_label = "【源码摘要】" if code_is_summary else "【源码】"

        return (
            "你是一个DMS数字工程师。请基于实测数据、国标条款与源码，输出一份Markdown评估报告。\n\n"
            "【实测数据摘要】\n"
            f"- 平均FPS: {avg_fps_text}\n"
            f"- 平均延迟: {avg_latency_text}\n\n"
            "【国标条款参考】\n"
            f"{standard_text}\n\n"
            f"{code_label}\n"
            f"{code_text}\n\n"
            "请输出以下内容：\n"
            "1) 合规性评估（对比国标条款）\n"
            "2) 发现的问题清单（含证据）\n"
            "3) 优化建议（优先级排序）\n"
            "4) 关键代码修改建议（可给出伪代码或片段）\n"
        )

    def _load_code_summary(self, summary_path: Path) -> str:
        """读取压缩后的源码摘要文本。"""

        if not summary_path.is_file():
            return ""
        try:
            return summary_path.read_text(encoding="utf-8").strip()
        except Exception as exc:  # noqa: BLE001
            LOGGER.error("Failed to read summary file %s: %s", summary_path, exc)
            return ""

    def _update_status(
        self, callback: Callable[[str], None] | None, message: str
    ) -> None:
        if callback is not None:
            callback(message)

    def _save_report(self, report: str) -> None:
        reports_dir = ROOT_DIR / "reports"
        reports_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_path = reports_dir / f"dms_report_{timestamp}.md"
        report_path.write_text(report, encoding="utf-8")
        LOGGER.info("Report saved to %s", report_path)


if __name__ == "__main__":
    agent = DMSDigitalEngineer()
    report = agent.analyze_and_optimize(
        log_file="data/logs/sample_dms_log.csv",
        code_file="data/source_code",
    )
    reports_dir = ROOT_DIR / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = reports_dir / f"dms_report_{timestamp}.md"
    report_path.write_text(report, encoding="utf-8")
    print(f"Report saved to: {report_path}")
