from __future__ import annotations

import sys
from pathlib import Path

from langchain.agents import create_agent
from langchain_openai import ChatOpenAI

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
from src.tools import (
    analyze_code_structure,
    compare_metrics,
    modify_code,
    parse_performance_logs,
    read_code_file,
    save_report,
    scan_codebase,
    search_standards,
    search_web,
)

# ═══════════════════════════════════════════════════════════
# DMS 领域 System Prompt
# ═══════════════════════════════════════════════════════════

DMS_SYSTEM_PROMPT = """你是一位资深的 DMS（驾驶员监测系统）数字工程师 Agent。
你的使命是：评估 DMS 系统的性能，发现与国标的差距，给出并执行优化方案。

## 领域知识

### DMS 标准架构
Camera -> Face Detection -> Feature Extraction -> State Determination -> Alert
  Face Detection: RetinaFace / MTCNN / MobileNet
  Feature Extraction: Eye (EAR闭眼比例), Mouth (MAR打哈欠比例), Head Pose (头部姿态)
  State Determination: Fatigue (PERCLOS疲劳判定), Distraction (Gaze Zone分心判定)
  Alert: Phone/Smoking detection (YOLO), visual + audio alerts

### DMS 核心指标体系
| 指标类别 | 具体指标 | 评判标准 |
|----------|----------|----------|
| 实时性 | FPS | >=15 合格，>=30 优秀，<15 严重缺陷 |
| 响应延迟 | 端到端延迟(ms) | <200ms 合格，200-500ms 偏高，>500ms 严重缺陷 |
| 疲劳检测 | 闭眼 EAR、打哈欠 MAR | 时间窗必须对标国标 |
| 分心检测 | 注视区域、头部姿态 | 需覆盖低头/抬头/转头三种姿态 |
| 违规检测 | 打电话、吸烟 | 需至少2种告警方式（视觉+听觉） |
| 资源 | CPU、内存 | 需适配嵌入式/边缘设备 |

### 国标关键要求（必须严格遵守）
1. 告警延迟必须 <= 行为持续时间的 50%（如闭眼持续2s，告警必须在1s内触发）
2. 至少 2 种提示方式（视觉提示 + 听觉提示）
3. 系统需有上电自检功能
4. 故障时必须有降级策略
5. 打哈欠检测的时间窗应为持续约3s（非1s）

## 强制评估流程

每次评估 DMS 系统时，你必须覆盖以下 7 个维度（不可跳过）：
[ ] 实时性评估（FPS、端到端延迟是否满足 DMS 场景要求）
[ ] 模型选型评估（backbone/检测模型是否适合嵌入式/实时场景）
[ ] 检测准确性评估（阈值设置是否合理，是否存在漏检/误检风险）
[ ] 国标合规性评估（逐一对照 RAG 检索到的国标条款）
[ ] 告警机制评估（告警方式是否>=2种，告警延迟是否满足要求）
[ ] 鲁棒性评估（光照变化、姿态变化下的适应能力）
[ ] 资源效率评估（CPU/内存占用是否合理）

## 工作原则

1. **先探索，后判断**：不要猜测，用工具获取事实。
2. **每次只读需要的代码**：定位到具体模块后，只读那个模块。
3. **评价必须对标 DMS 标准**：给具体的数值对比和影响分析。
4. **修改代码必须严谨**：
   - 修改前解释原因，关联到具体指标或国标条款
   - 评估风险等级（低/中/高）
   - 高风险修改必须征求用户确认
   - 绝对禁止：删除安全逻辑、降低告警灵敏度、移除国标要求的功能
5. **主动提供下一步方向**：每次分析后，告诉用户发现了什么，建议下一步。

## 对话风格

- 专业但不生硬，像经验丰富的工程师同事
- 用数据说话，不空谈
- 发现严重问题时明确指出
- 用户可能不是 DMS 专家，必要时用通俗语言解释
- 使用中文回复

## 推荐工作流
探索阶段: scan_codebase -> analyze_code_structure -> parse_performance_logs -> search_standards
深入阶段: read_code_file -> search_web
行动阶段: modify_code -> compare_metrics -> save_report
"""


class DMSAgent:
    """DMS 数字工程师 Agent —— 基于 LangChain 1.x create_agent。"""

    def __init__(
        self,
        model_name: str | None = None,
        temperature: float | None = None,
        top_p: float | None = None,
        max_tokens: int | None = None,
    ) -> None:
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
            streaming=True,
        )

        self.tools = [
            scan_codebase,
            analyze_code_structure,
            read_code_file,
            parse_performance_logs,
            search_standards,
            search_web,
            modify_code,
            compare_metrics,
            save_report,
        ]

        # LangChain 1.x: create_agent 返回 CompiledStateGraph
        self.agent = create_agent(
            model=self.llm,
            tools=self.tools,
            system_prompt=DMS_SYSTEM_PROMPT,
        )

        LOGGER.info("DMS Agent initialized with %d tools (LangChain %s)",
                     len(self.tools), "1.x")

    def run(self, message: str) -> dict:
        """执行一次对话，返回输出和中间步骤。

        返回值: {"output": str, "intermediate_steps": [...]}
        """
        result = self.agent.invoke({"messages": [{"role": "user", "content": message}]})

        # 提取最终输出和工具调用步骤
        messages = result.get("messages", [])
        output = ""
        steps = []

        for msg in messages:
            if hasattr(msg, "type"):
                if msg.type == "ai" and hasattr(msg, "content"):
                    output = msg.content or ""
                elif msg.type == "tool":
                    steps.append({
                        "tool": getattr(msg, "name", "unknown"),
                        "input": getattr(msg, "content", "")[:200],
                    })

        return {"output": output, "intermediate_steps": steps}

    def stream(self, message: str):
        """流式执行，逐步 yield 事件。"""
        return self.agent.astream_events(
            {"messages": [{"role": "user", "content": message}]},
            version="v2",
        )

    def clear_history(self) -> None:
        """重置会话（LangChain 1.x 无状态，每次 run 独立）。"""
        LOGGER.info("Session reset (stateless agent)")


if __name__ == "__main__":
    agent = DMSAgent()
    print("DMS Agent ready. Type 'quit' to exit.\n")

    while True:
        try:
            user_input = input(">>> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not user_input:
            continue
        if user_input.lower() in ("quit", "exit"):
            break

        result = agent.run(user_input)
        print(f"\n{result['output']}\n")
        if result["intermediate_steps"]:
            print(f"--- 调用了 {len(result['intermediate_steps'])} 个工具 ---")
