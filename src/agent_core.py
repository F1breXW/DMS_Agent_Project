from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

import pandas as pd
from langchain_openai import ChatOpenAI

# 运行脚本时把项目根目录加入 sys.path，确保可以导入 src.*
ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.config import DEEPSEEK_API_BASE, DEEPSEEK_API_KEY, LOGGER
from src.parsers import CodeParser, LogParseResult, LogParser
from src.rag_engine import StandardKnowledgeBase


class DMSDigitalEngineer:
    """整合日志解析、标准检索与 LLM 推理的数字工程师。"""

    def __init__(
        self,
        model_name: str = "deepseek-chat",
        temperature: float = 0.2,
    ) -> None:
        self.log_parser = LogParser()
        self.code_parser = CodeParser()
        self.knowledge_base = StandardKnowledgeBase()

        if not DEEPSEEK_API_KEY:
            LOGGER.warning("DEEPSEEK_API_KEY is empty; LLM call may fail.")

        self.llm = ChatOpenAI(
            base_url=DEEPSEEK_API_BASE,
            api_key=DEEPSEEK_API_KEY,
            model=model_name,
            temperature=temperature,
        )

    def analyze_and_optimize(self, log_file: str | Path, code_file: str | Path) -> str:
        """解析日志与源码，检索国标并调用大模型输出评估报告。"""

        log_path = Path(log_file)
        code_path = Path(code_file)

        # 先解析日志，获取平均指标
        log_result = self._parse_log_file(log_path)

        # 再解析源码
        code_text = self._read_code_content(code_path)

        # 再根据指标检索国标要求
        standard_query = self._build_standard_query(log_result.avg_latency_ms)
        standard_text = self.knowledge_base.search_standard(standard_query)

        # 最后组合 Prompt 调用大模型
        prompt = self._build_prompt(
            log_result=log_result,
            code_text=code_text,
            standard_text=standard_text,
        )

        response = self.llm.invoke(prompt)
        return getattr(response, "content", "")

    def _parse_log_file(self, log_path: Path) -> LogParseResult:
        """解析指定日志文件并计算平均指标。"""

        if log_path.is_file():
            try:
                df = pd.read_csv(log_path)
                items = list(self.log_parser._rows_to_models(df))
            except Exception as exc:  # noqa: BLE001
                LOGGER.error("Failed to parse log file %s: %s", log_path, exc)
                return LogParseResult(items=[], avg_fps=None, avg_latency_ms=None)

            if not items:
                return LogParseResult(items=[], avg_fps=None, avg_latency_ms=None)

            avg_fps = sum(x.fps for x in items) / len(items)
            avg_latency_ms = sum(x.latency_ms for x in items) / len(items)
            return LogParseResult(items=items, avg_fps=avg_fps, avg_latency_ms=avg_latency_ms)

        LOGGER.error("Log file not found: %s", log_path)
        return LogParseResult(items=[], avg_fps=None, avg_latency_ms=None)

    def _read_code_content(self, code_path: Path) -> str:
        """读取源码内容，支持单文件或目录。"""

        if code_path.is_dir():
            parser = CodeParser(code_path)
            code_map = parser.read_all()
            if not code_map:
                return ""

            parts: list[str] = []
            for path in sorted(code_map.keys()):
                parts.append(f"\n# File: {path}\n{code_map[path]}")
            return "\n".join(parts).strip()

        if code_path.is_file():
            parser = CodeParser(code_path.parent)
            code_map = parser.read_all()
            code_text = code_map.get(str(code_path))
            if code_text is not None:
                return code_text

            try:
                return code_path.read_text(encoding="utf-8")
            except Exception as exc:  # noqa: BLE001
                LOGGER.error("Failed to read code file %s: %s", code_path, exc)
                return ""

        LOGGER.error("Code path not found: %s", code_path)
        return ""

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

        return (
            "你是一个DMS数字工程师。请基于实测数据、国标条款与源码，输出一份Markdown评估报告。\n\n"
            "【实测数据摘要】\n"
            f"- 平均FPS: {avg_fps_text}\n"
            f"- 平均延迟: {avg_latency_text}\n\n"
            "【国标条款参考】\n"
            f"{standard_text}\n\n"
            "【源码】\n"
            f"{code_text}\n\n"
            "请输出以下内容：\n"
            "1) 合规性评估（对比国标条款）\n"
            "2) 发现的问题清单（含证据）\n"
            "3) 优化建议（优先级排序）\n"
            "4) 关键代码修改建议（可给出伪代码或片段）\n"
        )


if __name__ == "__main__":
    agent = DMSDigitalEngineer()
    report = agent.analyze_and_optimize(
        log_file="data/logs/sample_dms_log.csv",
        code_file="data/source_code",
    )
    print(report)
