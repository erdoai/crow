"""LLM client — unified interface for Anthropic and OpenAI with fallback."""

import json
import logging
from dataclasses import dataclass

import anthropic
import httpx

from crow.config.settings import Settings
from crow.llm.registry import ModelInfo, resolve_model

logger = logging.getLogger(__name__)


@dataclass
class LLMResponse:
    """Unified response from any LLM provider."""
    content: list[dict]  # [{type: "text", text: ...}, {type: "tool_use", ...}]
    stop_reason: str     # "end_turn" or "tool_use"
    usage_input: int = 0
    usage_output: int = 0


@dataclass
class StreamEvent:
    """Unified stream event."""
    type: str  # "text_delta", "tool_start", "tool_delta", "done"
    text: str | None = None
    tool_name: str | None = None
    tool_id: str | None = None
    partial_json: str | None = None
    stop_reason: str | None = None
    usage_input: int = 0
    usage_output: int = 0


async def call_llm(
    model_info: ModelInfo,
    system: str,
    messages: list[dict],
    tools: list[dict] | None = None,
    on_event=None,
) -> LLMResponse:
    """Call an LLM provider. Dispatches to the right implementation."""
    if model_info.provider == "anthropic":
        return await _call_anthropic(model_info, system, messages, tools, on_event)
    elif model_info.provider == "openai":
        return await _call_openai(model_info, system, messages, tools, on_event)
    else:
        raise ValueError(f"Unknown provider: {model_info.provider}")


async def call_llm_with_fallback(
    settings: Settings,
    system: str,
    messages: list[dict],
    tools: list[dict] | None = None,
    on_event=None,
) -> LLMResponse:
    """Call primary model, fall back to fallback_model on overload."""
    primary = resolve_model(settings.anthropic_model, settings)
    try:
        return await call_llm(primary, system, messages, tools, on_event)
    except anthropic.APIStatusError as e:
        if not settings.fallback_model or not settings.openai_api_key:
            raise
        is_overloaded = hasattr(e, "status_code") and e.status_code == 529
        if not is_overloaded:
            raise
        logger.warning(
            "Claude overloaded, falling back to %s",
            settings.fallback_model,
        )
        fallback = resolve_model(settings.fallback_model, settings)
        return await call_llm(fallback, system, messages, tools, on_event)


# -- Anthropic implementation --


async def _call_anthropic(
    model_info: ModelInfo,
    system: str,
    messages: list[dict],
    tools: list[dict] | None,
    on_event,
) -> LLMResponse:
    client = anthropic.AsyncAnthropic(
        api_key=model_info.api_key, max_retries=3
    )
    kwargs: dict = {
        "model": model_info.model,
        "max_tokens": 4096,
        "system": system,
        "messages": messages,
    }
    if tools:
        kwargs["tools"] = tools

    collected = []
    stop_reason = None
    usage_input = 0
    usage_output = 0

    async with client.messages.stream(**kwargs) as stream:
        async for event in stream:
            if event.type == "content_block_start":
                if event.content_block.type == "text":
                    collected.append({"type": "text", "text": ""})
                    if on_event:
                        await on_event(StreamEvent(type="text_start"))
                elif event.content_block.type == "tool_use":
                    collected.append({
                        "type": "tool_use",
                        "id": event.content_block.id,
                        "name": event.content_block.name,
                        "input": "",
                    })
                    if on_event:
                        await on_event(StreamEvent(
                            type="tool_start",
                            tool_name=event.content_block.name,
                            tool_id=event.content_block.id,
                        ))
            elif event.type == "content_block_delta":
                if event.delta.type == "text_delta":
                    collected[-1]["text"] += event.delta.text
                    if on_event:
                        await on_event(StreamEvent(
                            type="text_delta",
                            text=event.delta.text,
                        ))
                elif event.delta.type == "input_json_delta":
                    collected[-1]["input"] += event.delta.partial_json
            elif event.type == "message_delta":
                stop_reason = event.delta.stop_reason
                usage_output += event.usage.output_tokens
            elif event.type == "message_start":
                usage_input += event.message.usage.input_tokens

    # Parse tool inputs
    for block in collected:
        if block["type"] == "tool_use" and isinstance(block["input"], str):
            try:
                block["input"] = (
                    json.loads(block["input"]) if block["input"] else {}
                )
            except json.JSONDecodeError:
                block["input"] = {}

    return LLMResponse(
        content=collected,
        stop_reason=stop_reason or "end_turn",
        usage_input=usage_input,
        usage_output=usage_output,
    )


# -- OpenAI implementation --


def _convert_messages_for_openai(
    system: str, messages: list[dict]
) -> list[dict]:
    """Convert Anthropic-format messages to OpenAI format."""
    oai_messages = [{"role": "system", "content": system}]
    for msg in messages:
        content = msg.get("content")
        if isinstance(content, list):
            # Anthropic content blocks → OpenAI text
            text_parts = []
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    text_parts.append(block["text"])
                elif isinstance(block, str):
                    text_parts.append(block)
            oai_messages.append({
                "role": msg["role"],
                "content": "\n".join(text_parts) if text_parts else "",
            })
        else:
            oai_messages.append({
                "role": msg["role"],
                "content": content or "",
            })
    return oai_messages


def _convert_tools_for_openai(tools: list[dict]) -> list[dict]:
    """Convert Anthropic tool format to OpenAI function calling format."""
    oai_tools = []
    for tool in tools:
        oai_tools.append({
            "type": "function",
            "function": {
                "name": tool["name"],
                "description": tool.get("description", ""),
                "parameters": tool.get("input_schema", {}),
            },
        })
    return oai_tools


async def _call_openai(
    model_info: ModelInfo,
    system: str,
    messages: list[dict],
    tools: list[dict] | None,
    on_event,
) -> LLMResponse:
    """Call OpenAI API (non-streaming for simplicity on fallback path)."""
    oai_messages = _convert_messages_for_openai(system, messages)
    oai_tools = _convert_tools_for_openai(tools) if tools else None

    body: dict = {
        "model": model_info.model,
        "messages": oai_messages,
        "max_tokens": 4096,
    }
    if oai_tools:
        body["tools"] = oai_tools

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {model_info.api_key}",
                "Content-Type": "application/json",
            },
            json=body,
            timeout=120,
        )
        resp.raise_for_status()
        data = resp.json()

    choice = data["choices"][0]
    msg = choice["message"]
    usage = data.get("usage", {})

    # Convert OpenAI response to our unified format
    content: list[dict] = []
    if msg.get("content"):
        content.append({"type": "text", "text": msg["content"]})
        if on_event:
            await on_event(StreamEvent(
                type="text_delta", text=msg["content"]
            ))

    tool_calls = msg.get("tool_calls") or []
    stop_reason = "tool_use" if tool_calls else "end_turn"

    for tc in tool_calls:
        fn = tc["function"]
        try:
            inp = json.loads(fn["arguments"]) if fn["arguments"] else {}
        except json.JSONDecodeError:
            inp = {}
        content.append({
            "type": "tool_use",
            "id": tc["id"],
            "name": fn["name"],
            "input": inp,
        })
        if on_event:
            await on_event(StreamEvent(
                type="tool_start",
                tool_name=fn["name"],
                tool_id=tc["id"],
            ))

    return LLMResponse(
        content=content,
        stop_reason=stop_reason,
        usage_input=usage.get("prompt_tokens", 0),
        usage_output=usage.get("completion_tokens", 0),
    )
