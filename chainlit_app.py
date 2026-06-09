"""
DMS 数字工程师 Agent — Chainlit 对话界面

启动方式: chainlit run chainlit_app.py
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import chainlit as cl

ROOT_DIR = Path(__file__).resolve().parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.agent_core import DMSAgent
from src.config import LOGGER

WELCOME_MESSAGE = """# DMS Evaluator

驾驶员监测系统性能评估与优化 Agent。

**我能做什么：**
- 分析 DMS 系统的性能日志（FPS / 延迟 / 资源占用）
- 对照国标 GB/T 条款评估合规性
- 阅读源码定位性能瓶颈
- 给出可落地的代码修改建议并帮你改代码
- 搜索互联网上的优化方案

**开始方式：**
- 上传日志 CSV 和源码文件夹，然后告诉我"帮我分析这个系统"
- 直接提问，比如"FPS 太低怎么优化"
- 修改代码时，我会先解释原因、评估风险再动手
"""


@cl.on_chat_start
async def start():
    """初始化 Agent 并显示欢迎信息。"""
    # 注入自定义 CSS
    await cl.Html('<link rel="stylesheet" href="/public/theme.css">').send()

    agent = DMSAgent()
    cl.user_session.set("agent", agent)

    await cl.Message(content=WELCOME_MESSAGE).send()
    LOGGER.info("Chainlit session started")


@cl.on_message
async def on_message(message: cl.Message):
    """处理用户消息，运行 Agent 并展示结果和工具调用步骤。"""
    agent: DMSAgent = cl.user_session.get("agent")

    msg = cl.Message(content="")
    await msg.send()

    full_content: list[str] = []
    tool_steps: dict[str, cl.Step] = {}

    try:
        async for event in agent.stream(message.content):
            kind = event.get("event", "")

            if kind == "on_chat_model_stream":
                chunk = event.get("data", {}).get("chunk", {})
                content = getattr(chunk, "content", None)
                if content:
                    full_content.append(content)
                    msg.content = "".join(full_content)
                    await msg.update()

            elif kind == "on_tool_start":
                tool_name = event.get("name", "unknown")
                tool_input_raw = event.get("data", {}).get("input", "")
                tool_input = str(tool_input_raw)[:200]

                step = cl.Step(name=f"Tool: {tool_name}", type="tool")
                step.input = tool_input
                await step.send()
                tool_steps[tool_name] = step

            elif kind == "on_tool_end":
                tool_name = event.get("name", "unknown")
                tool_output_raw = event.get("data", {}).get("output", "")
                tool_output = str(tool_output_raw)[:500]

                if tool_name in tool_steps:
                    step = tool_steps[tool_name]
                    step.output = tool_output
                    await step.update()

    except Exception as e:
        LOGGER.error("Agent execution error: %s", e)
        msg.content = f"执行出错: {e}\n请检查网络连接和 API 配置后重试。"
        await msg.update()

    # 确保有输出
    if not msg.content:
        msg.content = "Agent 执行完成，但未生成输出。请重试。"
        await msg.update()


@cl.on_stop
async def on_stop():
    """用户停止时清理。"""
    agent: DMSAgent = cl.user_session.get("agent")
    if agent:
        agent.clear_history()
