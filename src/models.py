"""Pydantic data models for DMS log entries and evaluation reports."""

from __future__ import annotations

from datetime import datetime
from typing import List

from pydantic import BaseModel, Field


class DMSLogData(BaseModel):
    """DMS 日志数据结构，记录运行状态指标。"""

    timestamp: datetime = Field(..., description="日志记录时间")
    fps: float = Field(..., description="当前帧率")
    latency_ms: float = Field(..., description="端到端延迟（毫秒）")
    cpu_usage: float = Field(0.0, description="CPU 使用率（百分比）")
    memory_usage_mb: float = Field(0.0, description="内存使用量（MB）")


class EvaluationReport(BaseModel):
    """评估结果报告，包含合规评分与改进建议。"""

    compliance_score: float = Field(..., description="合规得分（0-100）")
    issues: List[str] = Field(default_factory=list, description="发现的问题列表")
    optimization_suggestions: List[str] = Field(
        default_factory=list, description="代码优化建议列表"
    )
    summary: str = Field("", description="评估总结")
    evaluated_at: datetime = Field(default_factory=datetime.utcnow, description="评估时间")


if __name__ == "__main__":
    # 简单自测：初始化模型并打印
    log_data = DMSLogData(
        timestamp=datetime.utcnow(),
        fps=30.0,
        latency_ms=85.5,
        cpu_usage=23.4,
        memory_usage_mb=512.0,
    )
    report = EvaluationReport(
        compliance_score=88.5,
        issues=["检测到轻微延迟峰值"],
        optimization_suggestions=["优化帧处理管线"],
        summary="整体表现良好，但仍有优化空间。",
    )

    print("DMSLogData:", log_data.model_dump())
    print("EvaluationReport:", report.model_dump())
