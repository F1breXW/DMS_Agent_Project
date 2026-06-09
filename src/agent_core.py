from __future__ import annotations

import sys
from pathlib import Path

from langchain.agents import AgentExecutor, create_react_agent
from langchain.memory import ConversationBufferWindowMemory
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
# DMS 领域 System Prompt（ReAct 版本）
# ═══════════════════════════════════════════════════════════

DMS_REACT_PREFIX = """你是一位资深的 DMS（驾驶员监测系统）数字工程师 Agent。
你的使命是：评估 DMS 系统的性能，发现与国标的差距，给出并执行优化方案。

## 领域知识

### DMS 标准架构
```
Camera → Face Detection → Feature Extraction → State Determination → Alert
  │         ├─ RetinaFace/MTCNN    ├─ Eye (EAR)        ├─ Fatigue (PERCLOS)
  │         └─ MobileNet/轻量模型   ├─ Mouth (MAR)      ├─ Distraction (Gaze Zone)
  │                                └─ Head Pose        └─ Phone/Smoking (YOLO)
```

### 核心指标体系
| 指标 | 合格标准 | 优秀标准 |
|------|----------|----------|
| FPS | ≥15 | ≥30 |
| 端到端延迟 | <200ms | <100ms |
| CPU占用 | <80% | <50% |
| 内存占用 | <2GB | <1GB |

### 国标关键要求
1. 告警延迟 ≤ 行为持续时间的 50%（闭眼2s→告警需在1s内触发）
2. 至少 2 种提示方式（视觉 + 听觉）
3. 系统需有上电自检功能
4. 故障时必须有降级策略
5. 打哈欠检测时间窗约3s（非1s）

## 强制评估维度（每次评估必须覆盖）
1. 实时性评估（FPS、延迟是否满足 DMS 场景要求）
2. 模型选型评估（backbone 是否适合嵌入式/实时场景）
3. 检测准确性评估（阈值是否合理，漏检/误检风险）
4. 国标合规性评估（逐一对照检索到的国标条款）
5. 告警机制评估（告警方式≥2种，告警延迟满足要求）
6. 鲁棒性评估（光照/姿态变化下的适应能力）
7. 资源效率评估（CPU/内存占用是否合理）

## 工作原则
1. 先探索后判断：用工具获取事实，不要猜测
2. 每次只读需要的代码：定位到具体模块后再精读
3. 评价对标 DMS 标准：说"FPS 8.96 远低于 DMS 要求的 15fps，每帧间隔 112ms，对于持续 2s 的闭眼行为只能捕获约 18 帧——可能导致疲劳判定不稳定"，而不是"FPS 有点低"
4. 修改代码前解释原因并评估风险，高风险操作必须征求确认
5. 绝对禁止：删除安全逻辑、降低告警灵敏度、移除国标要求功能
6. 主动建议下一步方向

## 对话风格
- 专业但不生硬，像经验丰富的工程师同事
- 用数据说话
- 发现严重问题时明确指出
- 必要时用通俗语言解释
- 中文回复

## 推荐工作流
探索阶段: scan_codebase → analyze_code_structure → parse_performance_logs → search_standards
深入阶段: read_code_file → search_web
行动阶段: modify_code → compare_metrics → save_report

你有 9 个工具可用。根据情况自主决定调用什么、何时调用。

TOOLS:
------"""

DMS_REACT_SUFFIX = """## 重要提醒

在给出最终答案之前，请确保你已经覆盖了以下维度（至少覆盖与当前问题相关的维度）：
- 实时性: FPS/延迟是否达标？
- 模型选型: 是否适合嵌入式场景？
- 检测准确性: 阈值是否合理？
- 国标合规: 是否符合国标要求？
- 告警机制: 是否≥2种提示方式？

如果用户刚上传了文件或指定了新的分析目标，先用工具探索，再做判断。

开始!"""


class DMSAgent:
    """DMS 数字工程师 Agent —— ReAct 模式，兼容所有 LLM。"""

    def __init__(
        self,
        model_name: str | None = None,
        temperature: float | None = None,
        top_p: float | None = None,
        max_tokens: int | None = None,
        max_history: int = 10,
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

        self.memory = ConversationBufferWindowMemory(
            k=max_history,
            return_messages=True,
            memory_key="chat_history",
            input_key="input",
            output_key="output",
        )

        from langchain_core.prompts import PromptTemplate

        prompt = PromptTemplate.from_template(
            DMS_REACT_PREFIX
            + "\n{tools}\n\n"
            + "使用以下格式回答:\n"
            + "Question: 需要回答的问题\n"
            + "Thought: 你应该思考要做什么\n"
            + "Action: 要使用的工具名称，必须是[{tool_names}]中的一个\n"
            + "Action Input: 工具的输入参数\n"
            + "Observation: 工具返回的结果\n"
            + "... (Thought/Action/Action Input/Observation 可以重复多次)\n"
            + "Thought: 我现在知道最终答案了\n"
            + "Final Answer: 对用户问题的最终回答\n\n"
            + "开始!\n\n"
            + "Chat History:\n{chat_history}\n\n"
            + "Question: {input}\n"
            + "Thought: {agent_scratchpad}"
        )

        self.agent = create_react_agent(
            llm=self.llm,
            tools=self.tools,
            prompt=prompt,
        )

        self.executor = AgentExecutor.from_agent_and_tools(
            agent=self.agent,
            tools=self.tools,
            memory=self.memory,
            verbose=True,
            handle_parsing_errors=True,
            max_iterations=15,
        )

        LOGGER.info("DMS Agent initialized with %d tools (ReAct mode)", len(self.tools))

    def run(self, message: str) -> dict:
        """执行一次对话交互，返回结果和中间步骤。"""
        result = self.executor.invoke({"input": message})
        return {
            "output": result.get("output", ""),
            "intermediate_steps": result.get("intermediate_steps", []),
        }

    def stream(self, message: str):
        """流式执行，逐步 yield 事件。用于 Chainlit 实时展示。"""
        return self.executor.astream_events(
            {"input": message},
            version="v2",
        )

    def clear_history(self) -> None:
        """清空对话历史。"""
        self.memory.clear()
        LOGGER.info("Conversation history cleared")


if __name__ == "__main__":
    agent = DMSAgent()
    print("DMS Agent ready (ReAct mode). Type 'quit' to exit.\n")

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
