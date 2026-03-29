"""Build agent context: messages, store injection."""

import json

import httpx


def _parse_structured_content(content) -> str | list[dict]:
    """Parse message content, returning structured blocks if JSON-encoded.

    Content may arrive as a string (legacy) or already-decoded list (JSONB).
    """
    if isinstance(content, list):
        return content
    if content and isinstance(content, str) and content.startswith("["):
        try:
            parsed = json.loads(content)
            if isinstance(parsed, list) and parsed and isinstance(parsed[0], dict):
                return parsed
        except (json.JSONDecodeError, KeyError):
            pass
    return content or ""


def build_api_messages(
    conversation_messages: list[dict],
    job_input: str,
) -> list[dict]:
    """Convert conversation messages to Anthropic API format with attachments."""
    api_messages = []
    for msg in conversation_messages:
        attachments = msg.get("attachments") or []
        if attachments:
            content_blocks = []
            raw = msg["content"]
            if raw:
                parsed = _parse_structured_content(raw)
                if isinstance(parsed, list):
                    content_blocks.extend(parsed)
                else:
                    content_blocks.append(
                        {"type": "text", "text": parsed}
                    )
            for att in attachments:
                ct = att["content_type"]
                if ct.startswith("image/"):
                    content_blocks.append({
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": ct,
                            "data": att["data"],
                        },
                    })
                elif ct == "application/pdf":
                    content_blocks.append({
                        "type": "document",
                        "source": {
                            "type": "base64",
                            "media_type": "application/pdf",
                            "data": att["data"],
                        },
                    })
                else:
                    content_blocks.append({
                        "type": "text",
                        "text": (
                            f"[Attached file: {att['filename']}"
                            f" ({ct}, {att['size_bytes']} bytes)]"
                        ),
                    })
            api_messages.append(
                {"role": msg["role"], "content": content_blocks}
            )
        else:
            # Structured content (tool_use/tool_result) is stored as JSON
            content = _parse_structured_content(msg["content"])
            api_messages.append(
                {"role": msg["role"], "content": content}
            )
    if not conversation_messages:
        api_messages.append({"role": "user", "content": job_input})
    return api_messages


async def _fetch_store_summary(
    server_url: str, worker_key: str, agent_name: str
) -> str | None:
    """Fetch agent store state for injection into context."""
    try:
        headers = {"x-worker-key": worker_key}
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{server_url}/api/store/{agent_name}",
                headers=headers,
                timeout=10,
            )
            if resp.status_code != 200:
                return None
            store_keys = resp.json()
            if not store_keys:
                return "Store is empty — no data from previous runs."
            parts = []
            for sk in store_keys[:20]:
                kr = await client.get(
                    f"{server_url}/api/store/{agent_name}/{sk['key']}",
                    headers=headers,
                    timeout=10,
                )
                if kr.status_code == 200:
                    data = kr.json().get("data")
                    # Truncate large values
                    text = json.dumps(data) if not isinstance(data, str) else data
                    if len(text) > 2000:
                        text = text[:2000] + "... (truncated)"
                    parts.append(f"**{sk['key']}**: {text}")
            return "\n\n".join(parts) if parts else None
    except Exception:
        return None


async def inject_store_state(
    api_messages: list[dict],
    agent_tools: list[str],
    server_url: str,
    worker_key: str,
    agent_name: str,
) -> None:
    """Inject agent store state before the last user message (in place)."""
    if "store_get" in set(agent_tools):
        store_text = await _fetch_store_summary(
            server_url, worker_key, agent_name
        )
        if store_text:
            # Insert before the last user message
            insert_idx = len(api_messages) - 1
            while insert_idx > 0 and api_messages[insert_idx]["role"] != "user":
                insert_idx -= 1
            api_messages.insert(insert_idx, {
                "role": "user",
                "content": (
                    f"[System: current store state — authoritative,"
                    f" trust over conversation history]\n{store_text}"
                ),
            })
            api_messages.insert(insert_idx + 1, {
                "role": "assistant",
                "content": "Understood, I'll use the store state as my source of truth.",
            })
