"""DeepSeek XML hallucination defense: parse and strip XML-format tool calls.

DeepSeek sometimes outputs <function_calls><invoke name="X"><parameter...>
as text instead of native tool_calls. This module parses XML into real
tool_call dicts or strips the noise from final responses.
"""

from __future__ import annotations

import re

from src.config import LOGGER


def strip_xml(text: str) -> str:
    """Strip XML-format tool call text that DeepSeek hallucinates.

    Handles both <function_calls> and <tool_calls> variants, plus
    complete / incomplete fragments.
    """
    # Pass 1: complete blocks with closing tags
    text = re.sub(
        r'<(?:function_calls|tool_calls)>[\s\S]*?</(?:function_calls|tool_calls)>',
        '', text, flags=re.IGNORECASE,
    )
    text = re.sub(
        r'<invoke\b[^>]*>[\s\S]*?</invoke>',
        '', text, flags=re.IGNORECASE,
    )
    text = re.sub(
        r'<parameter\b[^>]*>[\s\S]*?</parameter>',
        '', text, flags=re.IGNORECASE,
    )
    # Pass 2: orphaned opening/closing tags (incomplete fragments)
    text = re.sub(
        r'</?(?:function_calls|tool_calls|invoke|parameter)\b[^>]*>',
        '', text, flags=re.IGNORECASE,
    )
    return text.strip()


def parse_xml_to_tool_calls(text: str, tools_by_name: dict) -> tuple[str, list[dict] | None]:
    """Parse Anthropic-style XML tool calls in model output.

    When DeepSeek outputs <function_calls><invoke name="X"><parameter...>
    as text (instead of native tool_calls), parse the XML and return
    proper tool_call dicts that ToolNode can execute.

    Returns (cleaned_text, tool_calls_or_None).
    """
    if not text or not re.search(r'<(?:function_calls|tool_calls)>', text, re.IGNORECASE):
        return text, None

    pattern = r'<(?:function_calls|tool_calls)>(.*?)</(?:function_calls|tool_calls)>'
    match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
    if not match:
        # Opening tag exists but no closing tag (streaming fragment)
        return strip_xml(text), None

    xml_block = match.group(0)
    block = match.group(1)

    tool_calls = []
    invoke_pattern = r'<invoke\s+name="(\w+)"[^>]*>(.*?)</invoke>'
    for i, inv in enumerate(re.finditer(invoke_pattern, block, re.IGNORECASE | re.DOTALL)):
        tool_name = inv.group(1)
        params_block = inv.group(2)

        if tool_name not in tools_by_name:
            LOGGER.warning("XML hijack: unknown tool '%s', skipping", tool_name)
            continue

        params = {}
        param_pattern = r'<parameter\s+name="(\w+)"[^>]*>(.*?)</parameter>'
        for pm in re.finditer(param_pattern, params_block, re.IGNORECASE | re.DOTALL):
            params[pm.group(1)] = pm.group(2).strip()

        tool_calls.append({
            "name": tool_name,
            "args": params,
            "id": f"xml_{i}",
            "type": "tool_call",
        })
        LOGGER.info("XML hijack: parsed %s with %d params", tool_name, len(params))

    if not tool_calls:
        return strip_xml(text), None

    tool_names = ", ".join(tc["name"] for tc in tool_calls)
    cleaned = text.replace(xml_block, "")
    LOGGER.info("XML hijack: replaced %d tool(s) [%s]", len(tool_calls), tool_names)

    return cleaned, tool_calls
