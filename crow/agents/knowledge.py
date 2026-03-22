"""PARA knowledge helpers — search and write with optional embeddings."""

import logging

import httpx

from crow.config.settings import Settings
from crow.db.database import Database

logger = logging.getLogger(__name__)


async def generate_embedding(text: str, settings: Settings) -> list[float] | None:
    """Generate embedding via OpenAI-compatible API."""
    if not settings.anthropic_api_key:
        return None

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "https://api.openai.com/v1/embeddings",
                headers={"Authorization": f"Bearer {settings.anthropic_api_key}"},
                json={"model": settings.embedding_model, "input": text},
                timeout=10,
            )
            resp.raise_for_status()
            return resp.json()["data"][0]["embedding"]
    except Exception:
        logger.exception("Failed to generate embedding")
        return None


async def search_knowledge(
    db: Database,
    settings: Settings,
    query: str,
    agent_name: str | None = None,
    category: str | None = None,
    limit: int = 10,
) -> list[dict]:
    """Search knowledge using both semantic and keyword search."""
    embedding = await generate_embedding(query, settings)
    return await db.search_knowledge(
        query_embedding=embedding,
        text_query=query,
        agent_name=agent_name,
        category=category,
        limit=limit,
    )


async def write_knowledge(
    db: Database,
    settings: Settings,
    agent_name: str,
    category: str,
    title: str,
    content: str,
    source: str | None = None,
    tags: list[str] | None = None,
) -> str:
    """Write a knowledge entry with auto-generated embedding."""
    embedding = await generate_embedding(f"{title}\n{content}", settings)
    return await db.upsert_knowledge(
        agent_name=agent_name,
        category=category,
        title=title,
        content=content,
        source=source,
        tags=tags,
        embedding=embedding,
    )
