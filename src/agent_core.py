"""DMS AI Agent — LangGraph StateGraph with domain system prompt, tool call enforcement, XML hallucination defense."""

from __future__ import annotations

import re
import sys
from pathlib import Path

from typing import Annotated

from langchain_core.messages import AIMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.constants import END, START
from langgraph.graph import StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from typing_extensions import Required, TypedDict

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
    clear_session_kb,
    compare_metrics,
    modify_code,
    parse_performance_logs,
    read_code_file,
    save_report,
    scan_codebase,
    search_standards,
    search_web,
    set_session_kb,
)
from src.xml_defense import parse_xml_to_tool_calls, strip_xml

# ═══════════════════════════════════════════════════════════
# DMS 领域 System Prompt
# ═══════════════════════════════════════════════════════════

DMS_SYSTEM_PROMPT = """你是一位资深的 DMS（驾驶员监测系统）数字工程师。你的工作是帮助用户评估 DMS 系统性能、发现合规差距、给出可落地的优化方案。

## 核心原则

### 1. 专业精度是第一优先级
这是 DMS 专业评估工具，不是通用聊天助手。你的每一次回答都应体现专业水准：
- 有数据支撑的判断，必须引用具体数值，不做模糊结论
- 涉及标准合规的，必须对照 GB/T 具体条款
- 涉及技术方案的，必须给出可操作的指导
- 即使是知识性问答，回答准确之后可以追问用户是否需要进一步分析

### 2. 用工具获取事实，不猜测
你可以不调工具的唯一情况：问题是纯知识性问答且你完全确定答案。其余涉及用户代码、用户数据、用户系统的分析，都必须通过工具获取事实。

调用工具的广度由问题复杂度决定。核心自问：**我的判断是否有足够的证据支撑？** 如果不够，继续获取。

### 3. 聚焦用户问题，不跑题
用户问什么就深入什么。用户问 FPS 就深入分析 FPS，不自动扩展到延迟、内存、模型选型。但如果在分析中发现其他维度存在严重影响判断的因素，应该指出并询问用户是否要一并分析。

建议下一步方向，但不要列一长串清单。

## 工具使用规则

### 通用规则
- **不重复调用**：同一工具不对同一目标重复调用。parse_performance_logs 对同一个 CSV 只调 1 次，scan_codebase 对同一个目录只调 1 次，search_standards / search_web 对同一个关键词各调 1 次
- **错误不重试**：工具返回结果以 [ERR] 或 [FAIL] 开头时，直接告知用户失败原因，不要重试
- **用已有信息**：不需要为回答一个问题把所有相关工具都调一遍。已有信息能支撑结论时直接回答
- **无文件时提醒**：用户没上传文件时，提醒用户上传，不要假设已有文件

### 修改代码规则（严格遵守）
- 每次只描述并执行 1 处修改，绝不要一次描述多处
- 严格遵守流程：描述修改 → 调用 modify_code → 根据结果确认成功/失败 → 再继续下一处
- 每处修改的描述独占一行，用「---」分隔不同修改
- 如果 modify_code 返回 [ERR]（片段未找到），说明文件已被前面的修改改变，需要先用 read_code_file 重新确认当前内容，再调整 old_snippet
- 每次调用 modify_code 前，确保 old_snippet 精准匹配当前文件实际内容
- **关联修改必须成对完成**：如果修改 A（如改函数签名）依赖修改 B（如改调用方），必须在同一轮对话中全部完成。不要改了一半就停止——宁可少改几组，也不要留下一组改了一半
- 修改代码前必须解释原因、关联指标、评估风险。绝对禁止删除安全逻辑或降低告警灵敏度

### save_report 使用时机
仅在用户明确要求"完整评估"、"全面审查"或点击了前端"生成报告"按钮时使用。日常分析对话不需要保存报告。

## 工具

**检索类**：scan_codebase、analyze_code_structure、read_code_file、parse_performance_logs、search_standards、search_web
**分析类**：compare_metrics
**执行类**：modify_code、save_report

- search_standards 同时检索全局 GB/T 国标和用户上传的知识文档
- search_standards 和 search_web 是两个独立工具，按需单独或组合调用，不是固定搭配

## DMS 领域知识

### 标准架构
Camera → Face Detection → Feature Extraction → State Determination → Alert
- Face Detection: RetinaFace / MTCNN / MobileNet
- Feature Extraction: Eye (EAR闭眼比例), Mouth (MAR打哈欠比例), Head Pose (头部姿态)
- State Determination: Fatigue (PERCLOS疲劳判定), Distraction (Gaze Zone分心判定)
- Alert: Phone/Smoking detection (YOLO), visual + audio alerts

### 核心指标体系
| 指标 | 评判标准 |
|------|---------|
| FPS | ≥30 优秀，≥15 合格，<15 严重缺陷 |
| 端到端延迟 | ≤200ms 合格，200-500ms 偏高，>500ms 严重缺陷 |
| 疲劳检测 | 闭眼EAR、打哈欠MAR，时间窗须对标国标 |
| 分心检测 | 需覆盖低头/抬头/转头三种姿态 |
| 违规检测 | 打电话、吸烟，需至少2种告警方式（视觉+听觉） |
| 资源 | CPU、内存需适配嵌入式/边缘设备 |

### GB/T 国标关键要求
1. 告警延迟 ≤ 行为持续时间的 50%（如闭眼持续2s，告警须在1s内触发）
2. 至少 2 种提示方式（视觉 + 听觉）
3. 系统需有上电自检功能
4. 故障时必须有降级策略
5. 打哈欠检测时间窗应为持续约 3s

## 对话风格

- 专业、直接、有数据
- 发现严重问题时明确指出（"FPS 仅 8.96，连合格线 15 的一半都不到，这个问题必须优先解决"）
- 用户可能不是 DMS 专家，必要时用通俗语言解释
- 始终用中文回复
"""


class DMSAgentState(TypedDict):
    """Custom agent state with tool call enforcement."""
    messages: Required[Annotated[list, add_messages]]
    tool_call_count: int
    tool_call_history: list[dict[str, str]]
    round_count: int  # Number of model→tools→model cycles


# Tools allowed to be called multiple times (content/queries may differ)
_REPEATABLE_TOOLS = frozenset({"read_code_file", "scan_codebase", "search_web", "search_standards"})


class DMSAgent:
    """DMS 数字工程师 Agent —— 基于 LangGraph StateGraph + 工具调用硬限制。"""

    def __init__(
        self,
        model_name: str | None = None,
        temperature: float | None = None,
        top_p: float | None = None,
        max_tokens: int | None = None,
        session_kb=None,  # SessionKnowledgeBase | None
    ) -> None:
        self.session_kb = session_kb
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
        self._tools_by_name = {t.name: t for t in self.tools}

        # Build custom graph with tool call enforcement
        self.agent = self._build_graph()

        LOGGER.info("DMS Agent initialized with %d tools (custom StateGraph)",
                     len(self.tools))

    def _build_graph(self):
        """Build a StateGraph that enforces tool call discipline.

        Unlike create_agent which trusts the model to stop, this graph:
        - Detects repeated calls to the same tool+target
        - Forces the model to respond when duplicate calls are detected
        - Hard recursion_limit=100 as safety net
        """
        tool_node = ToolNode(tools=self.tools)
        system_message = SystemMessage(content=DMS_SYSTEM_PROMPT)
        llm_with_tools = self.llm.bind_tools(self.tools)
        llm_no_tools = self.llm  # For force_respond: model must NOT have tools

        def call_model(state: DMSAgentState) -> dict:
            messages = [system_message] + state["messages"]
            response = llm_with_tools.invoke(messages)
            content = response.content or ""

            if re.search(r'<(?:function_calls|tool_calls)>', content, re.IGNORECASE):
                if not getattr(response, "tool_calls", None):
                    # No native tool calls — parse XML into real tool calls
                    cleaned, tool_calls = parse_xml_to_tool_calls(
                        content, self._tools_by_name)
                    if tool_calls:
                        response = AIMessage(content=cleaned, tool_calls=tool_calls)
                else:
                    # Has native tool calls — just strip XML noise from text
                    cleaned = strip_xml(content)
                    if cleaned != content:
                        response = AIMessage(
                            content=cleaned,
                            tool_calls=response.tool_calls,
                        )

            return {"messages": [response]}

        def should_continue(state: DMSAgentState) -> str:
            messages = state["messages"]
            last_message = messages[-1] if messages else None

            if not isinstance(last_message, AIMessage) or not last_message.tool_calls:
                return END

            # Detect duplicate tool+target calls (repeatable tools exempted)
            history = state.get("tool_call_history", [])
            for tc in last_message.tool_calls:
                if tc["name"] in _REPEATABLE_TOOLS:
                    continue
                target = str(tc.get("args", {}))
                for h in history:
                    if h["tool"] == tc["name"] and h["target"] == target:
                        LOGGER.info("Agent repeated tool %s on same target, forcing response", tc["name"])
                        return "force_respond"

            return "tools"

        def after_tools(state: DMSAgentState) -> dict:
            """Update tool call counters after tools execute."""
            history = list(state.get("tool_call_history", []))
            new_count = state.get("tool_call_count", 0)
            new_round = state.get("round_count", 0) + 1

            messages = state["messages"]
            for msg in reversed(messages):
                if isinstance(msg, AIMessage) and msg.tool_calls:
                    for tc in msg.tool_calls:
                        new_count += 1
                        target = str(tc.get("args", {}))
                        history.append({"tool": tc["name"], "target": target})
                    break

            LOGGER.info("Agent round %d complete: %d total tool calls so far", new_round, new_count)
            return {
                "tool_call_count": new_count,
                "tool_call_history": history,
                "round_count": new_round,
            }

        _FORCE_RESPOND_PROMPT = SystemMessage(content=(
            "[系统指令] 你已经完成了所有工具调用。现在基于已获取的结果，"
            "整合分析，直接给用户一个总结性的回答。用自然语言回复。"
        ))

        def force_respond(state: DMSAgentState) -> dict:
            """Force the model to respond with text, no more tool calls."""
            # Strip orphaned AIMessages with unexecuted tool_calls
            messages = list(state["messages"])
            while messages and isinstance(messages[-1], AIMessage) and getattr(messages[-1], "tool_calls", None):
                messages.pop()

            # Prefer tool_choice="none", fall back to llm_no_tools
            try:
                restricted = self.llm.bind_tools(self.tools, tool_choice="none")
                response = restricted.invoke([_FORCE_RESPOND_PROMPT] + messages)
            except Exception:
                response = llm_no_tools.invoke([_FORCE_RESPOND_PROMPT] + messages)

            content = strip_xml(response.content or "")
            return {"messages": [AIMessage(content=content)]}

        graph = StateGraph(DMSAgentState)

        graph.add_node("model", call_model)
        graph.add_node("tools", tool_node)
        graph.add_node("after_tools", after_tools)
        graph.add_node("force_respond", force_respond)

        graph.add_edge(START, "model")
        graph.add_conditional_edges(
            "model",
            should_continue,
            {"tools": "tools", "force_respond": "force_respond", END: END},
        )
        graph.add_edge("tools", "after_tools")
        graph.add_edge("after_tools", "model")
        graph.add_edge("force_respond", END)

        return graph.compile()

    def _initial_state(self, message: str) -> dict:
        """Build initial state with tool call counters reset."""
        return {
            "messages": [{"role": "user", "content": message}],
            "tool_call_count": 0,
            "tool_call_history": [],
            "round_count": 0,
        }

    def run(self, message: str) -> dict:
        """执行一次对话，返回输出和中间步骤。"""
        result = self.agent.invoke(
            self._initial_state(message),
            config={"recursion_limit": 100},
        )

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
            self._initial_state(message),
            version="v2",
            config={"recursion_limit": 100},
        )

    async def stream_with_context(
        self,
        message: str,
        upload_dir: str = "",
        files: list[str] | None = None,
        history: list[dict] | None = None,
        knowledge_files: list[str] | None = None,
    ):
        """注入会话上下文后流式执行。

        参数:
          message: 用户消息
          upload_dir: 上传目录路径
          files: 已上传文件列表
          history: 之前的对话历史 [{"role": "user"/"agent", "content": ...}, ...]
          knowledge_files: 用户上传的知识文档名列表
        """
        files = files or []
        knowledge_files = knowledge_files or []
        history = history or []

        # Build message list from conversation history
        all_messages = []
        for m in history:
            role = "assistant" if m["role"] == "agent" else "user"
            all_messages.append({"role": role, "content": m["content"]})

        # Build current message with file context
        context_parts = []
        if files:
            file_list = "\n".join(f"  - {f}" for f in files)
            context_parts.append(f"用户已上传以下文件（位于 {upload_dir}）：\n{file_list}")
        if knowledge_files:
            kf_list = "\n".join(f"  - {f}" for f in knowledge_files)
            context_parts.append(f"用户已上传以下知识文档（可通过 search_standards 检索）：\n{kf_list}")
        if context_parts:
            full_message = f"[会话上下文]\n" + "\n\n".join(context_parts) + f"\n\n用户消息：\n{message}"
        else:
            full_message = message

        all_messages.append({"role": "user", "content": full_message})

        if self.session_kb is not None:
            set_session_kb(self.session_kb)
        try:
            async for event in self.agent.astream_events(
                {
                    "messages": all_messages,
                    "tool_call_count": 0,
                    "tool_call_history": [],
                    "round_count": 0,
                },
                version="v2",
                config={"recursion_limit": 100},
            ):
                yield event
        finally:
            if self.session_kb is not None:
                clear_session_kb()

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
