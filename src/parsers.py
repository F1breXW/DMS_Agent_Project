"""CSV log parser and Python source code reader for DMS data ingestion."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional

import pandas as pd

from src.config import LOGGER
from src.models import DMSLogData


@dataclass
class LogParseResult:
    """日志解析结果：包含对象列表与统计值。"""

    items: List[DMSLogData]
    avg_fps: Optional[float]
    avg_latency_ms: Optional[float]


class LogParser:
    """解析 DMS 日志 CSV，并转换为结构化对象。"""

    def __init__(self, log_dir: Path | str = "data/logs") -> None:
        self.log_dir = Path(log_dir)

    def parse_all(self) -> LogParseResult:
        """读取目录下所有 CSV，返回解析后的结果与平均值。"""

        items: List[DMSLogData] = []
        csv_files = sorted(self.log_dir.glob("*.csv"))

        if not csv_files:
            LOGGER.error("No CSV files found in %s", self.log_dir)
            return LogParseResult(items=items, avg_fps=None, avg_latency_ms=None)

        for csv_path in csv_files:
            try:
                df = pd.read_csv(csv_path)
            except Exception as exc:  # noqa: BLE001
                LOGGER.error("Failed to read CSV %s: %s", csv_path, exc)
                continue

            required_cols = {
                "timestamp",
                "fps",
                "latency_ms",
                "cpu_usage",
                "mem_usage",
            }
            if not required_cols.issubset(set(df.columns)):
                LOGGER.error(
                    "CSV %s missing required columns: %s",
                    csv_path,
                    sorted(required_cols - set(df.columns)),
                )
                continue

            items.extend(self._rows_to_models(df))

        if not items:
            return LogParseResult(items=items, avg_fps=None, avg_latency_ms=None)

        avg_fps = sum(x.fps for x in items) / len(items)
        avg_latency_ms = sum(x.latency_ms for x in items) / len(items)
        return LogParseResult(items=items, avg_fps=avg_fps, avg_latency_ms=avg_latency_ms)

    def _rows_to_models(self, df: pd.DataFrame) -> Iterable[DMSLogData]:
        """将 DataFrame 的每一行转换为 DMSLogData。"""

        models: List[DMSLogData] = []
        for _, row in df.iterrows():
            try:
                timestamp = pd.to_datetime(row["timestamp"], errors="raise")
                model = DMSLogData(
                    timestamp=timestamp.to_pydatetime(),
                    fps=float(row["fps"]),
                    latency_ms=float(row["latency_ms"]),
                    cpu_usage=float(row["cpu_usage"]),
                    memory_usage_mb=float(row["mem_usage"]),
                )
                models.append(model)
            except Exception as exc:  # noqa: BLE001
                LOGGER.error("Bad row data: %s", exc)
        return models


class CodeParser:
    """读取 data/source_code 目录下的 .py 文件内容。"""

    def __init__(self, source_dir: Path | str = "data/source_code") -> None:
        self.source_dir = Path(source_dir)

    def read_all(self) -> dict[str, str]:
        """读取所有 .py 文件，并以文本形式返回。"""

        results: dict[str, str] = {}
        py_files = sorted(self.source_dir.rglob("*.py"))

        if not py_files:
            LOGGER.error("No .py files found in %s", self.source_dir)
            return results

        for path in py_files:
            try:
                results[str(path)] = path.read_text(encoding="utf-8")
            except Exception as exc:  # noqa: BLE001
                LOGGER.error("Failed to read %s: %s", path, exc)
        return results


if __name__ == "__main__":
    # 读取真实日志文件
    log_parser = LogParser()
    log_result = log_parser.parse_all()
    print("Parsed logs:", len(log_result.items))
    print("Avg FPS:", log_result.avg_fps)
    print("Avg latency (ms):", log_result.avg_latency_ms)

    # 读取真实源码文件
    code_parser = CodeParser()
    code_result = code_parser.read_all()
    print("Parsed code files:", list(code_result.keys()))
