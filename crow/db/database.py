import logging
from datetime import UTC, datetime
from uuid import uuid4

import asyncpg

from crow.db.migrate import run_migrations

logger = logging.getLogger(__name__)


class Database:
    def __init__(self, pool: asyncpg.Pool):
        self._pool = pool

    @classmethod
    async def connect(cls, database_url: str) -> "Database":
        pool = await asyncpg.create_pool(database_url)
        db = cls(pool)
        await run_migrations(pool)
        logger.info("Database connected and migrations applied")
        return db

    async def close(self) -> None:
        await self._pool.close()

    # -- Conversations --

    async def get_or_create_conversation(
        self, gateway: str, gateway_thread_id: str, user_id: str | None = None
    ) -> dict:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM conversations WHERE gateway = $1 AND gateway_thread_id = $2",
                gateway,
                gateway_thread_id,
            )
            if row:
                return dict(row)

            conv_id = uuid4().hex
            now = datetime.now(UTC)
            await conn.execute(
                """INSERT INTO conversations
                   (id, gateway, gateway_thread_id, user_id, created_at, updated_at)
                   VALUES ($1, $2, $3, $4, $5, $6)""",
                conv_id,
                gateway,
                gateway_thread_id,
                user_id,
                now,
                now,
            )
            return {
                "id": conv_id,
                "gateway": gateway,
                "gateway_thread_id": gateway_thread_id,
                "user_id": user_id,
                "created_at": now,
                "updated_at": now,
            }

    async def get_conversation(self, conversation_id: str) -> dict | None:
        row = await self._pool.fetchrow(
            "SELECT * FROM conversations WHERE id = $1", conversation_id
        )
        return dict(row) if row else None

    async def list_conversations(
        self, limit: int = 50, user_id: str | None = None
    ) -> list[dict]:
        if user_id:
            rows = await self._pool.fetch(
                "SELECT * FROM conversations WHERE user_id = $1 ORDER BY updated_at DESC LIMIT $2",
                user_id,
                limit,
            )
        else:
            rows = await self._pool.fetch(
                "SELECT * FROM conversations ORDER BY updated_at DESC LIMIT $1", limit
            )
        return [dict(r) for r in rows]

    # -- Messages --

    async def insert_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
        agent_name: str | None = None,
    ) -> str:
        msg_id = uuid4().hex
        await self._pool.execute(
            """INSERT INTO messages (id, conversation_id, role, content, agent_name, created_at)
               VALUES ($1, $2, $3, $4, $5, $6)""",
            msg_id,
            conversation_id,
            role,
            content,
            agent_name,
            datetime.now(UTC),
        )
        # Touch conversation updated_at
        await self._pool.execute(
            "UPDATE conversations SET updated_at = $1 WHERE id = $2",
            datetime.now(UTC),
            conversation_id,
        )
        return msg_id

    async def get_messages(
        self, conversation_id: str, limit: int = 50
    ) -> list[dict]:
        rows = await self._pool.fetch(
            """SELECT * FROM messages
               WHERE conversation_id = $1
               ORDER BY created_at ASC
               LIMIT $2""",
            conversation_id,
            limit,
        )
        return [dict(r) for r in rows]

    # -- Jobs --

    async def create_job(
        self,
        agent_name: str,
        input_text: str,
        conversation_id: str | None = None,
    ) -> str:
        job_id = uuid4().hex
        await self._pool.execute(
            """INSERT INTO jobs (id, agent_name, conversation_id, status, input, created_at)
               VALUES ($1, $2, $3, 'pending', $4, $5)""",
            job_id,
            agent_name,
            conversation_id,
            input_text,
            datetime.now(UTC),
        )
        return job_id

    async def claim_next_job(self, worker_id: str) -> dict | None:
        """Atomically claim the next pending job for a worker."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """UPDATE jobs
                   SET status = 'running', worker_id = $1, started_at = $2
                   WHERE id = (
                       SELECT id FROM jobs WHERE status = 'pending'
                       ORDER BY created_at ASC
                       LIMIT 1
                       FOR UPDATE SKIP LOCKED
                   )
                   RETURNING *""",
                worker_id,
                datetime.now(UTC),
            )
            return dict(row) if row else None

    async def complete_job(
        self,
        job_id: str,
        output: str,
        tokens_used: int = 0,
    ) -> None:
        await self._pool.execute(
            """UPDATE jobs
               SET status = 'completed', output = $1, tokens_used = $2, completed_at = $3
               WHERE id = $4""",
            output,
            tokens_used,
            datetime.now(UTC),
            job_id,
        )

    async def fail_job(self, job_id: str, error: str) -> None:
        await self._pool.execute(
            """UPDATE jobs
               SET status = 'failed', error = $1, completed_at = $2
               WHERE id = $3""",
            error,
            datetime.now(UTC),
            job_id,
        )

    async def get_job(self, job_id: str) -> dict | None:
        row = await self._pool.fetchrow("SELECT * FROM jobs WHERE id = $1", job_id)
        return dict(row) if row else None

    async def list_jobs(
        self, status: str | None = None, limit: int = 50
    ) -> list[dict]:
        if status:
            rows = await self._pool.fetch(
                "SELECT * FROM jobs WHERE status = $1 ORDER BY created_at DESC LIMIT $2",
                status,
                limit,
            )
        else:
            rows = await self._pool.fetch(
                "SELECT * FROM jobs ORDER BY created_at DESC LIMIT $1", limit
            )
        return [dict(r) for r in rows]

    # -- Workers --

    async def register_worker(self, worker_id: str, name: str | None = None) -> None:
        await self._pool.execute(
            """INSERT INTO workers (id, name, last_heartbeat, status)
               VALUES ($1, $2, $3, 'idle')
               ON CONFLICT (id) DO UPDATE SET last_heartbeat = $3, status = 'idle'""",
            worker_id,
            name,
            datetime.now(UTC),
        )

    async def worker_heartbeat(self, worker_id: str, status: str = "idle") -> None:
        await self._pool.execute(
            "UPDATE workers SET last_heartbeat = $1, status = $2 WHERE id = $3",
            datetime.now(UTC),
            status,
            worker_id,
        )

    async def list_workers(self) -> list[dict]:
        rows = await self._pool.fetch("SELECT * FROM workers ORDER BY last_heartbeat DESC")
        return [dict(r) for r in rows]

    # -- Knowledge (PARA + pgvector) --

    async def search_knowledge(
        self,
        query_embedding: list[float] | None = None,
        text_query: str | None = None,
        agent_name: str | None = None,
        category: str | None = None,
        user_id: str | None = None,
        limit: int = 10,
    ) -> list[dict]:
        """Search knowledge by semantic similarity and/or text match."""
        conditions = []
        params: list = []
        param_idx = 0

        if agent_name:
            param_idx += 1
            conditions.append(f"agent_name = ${param_idx}")
            params.append(agent_name)

        if user_id:
            param_idx += 1
            conditions.append(f"user_id = ${param_idx}")
            params.append(user_id)

        if category:
            param_idx += 1
            conditions.append(f"category = ${param_idx}")
            params.append(category)

        if text_query:
            param_idx += 1
            conditions.append(f"(content ILIKE ${param_idx} OR title ILIKE ${param_idx})")
            params.append(f"%{text_query}%")

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

        if query_embedding:
            param_idx += 1
            order = f"ORDER BY embedding <=> ${param_idx}"
            params.append(str(query_embedding))
        else:
            order = "ORDER BY updated_at DESC"

        param_idx += 1
        params.append(limit)

        cols = "id, agent_name, category, title, content, source, tags"
        cols += ", created_at, updated_at"
        sql = f"SELECT {cols} FROM knowledge {where} {order} LIMIT ${param_idx}"
        rows = await self._pool.fetch(
            sql,
            *params,
        )
        return [dict(r) for r in rows]

    async def upsert_knowledge(
        self,
        agent_name: str,
        category: str,
        title: str,
        content: str,
        source: str | None = None,
        tags: list[str] | None = None,
        embedding: list[float] | None = None,
        user_id: str | None = None,
    ) -> str:
        knowledge_id = uuid4().hex
        now = datetime.now(UTC)
        if embedding:
            await self._pool.execute(
                """INSERT INTO knowledge
                   (id, agent_name, category, title, content,
                    source, tags, embedding, user_id, created_at, updated_at)
                   VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)""",
                knowledge_id,
                agent_name,
                category,
                title,
                content,
                source,
                tags or [],
                str(embedding),
                user_id,
                now,
                now,
            )
        else:
            await self._pool.execute(
                """INSERT INTO knowledge
                   (id, agent_name, category, title, content,
                    source, tags, user_id, created_at, updated_at)
                   VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)""",
                knowledge_id,
                agent_name,
                category,
                title,
                content,
                source,
                tags or [],
                user_id,
                now,
                now,
            )
        return knowledge_id

    async def archive_knowledge(self, knowledge_id: str) -> None:
        await self._pool.execute(
            "UPDATE knowledge SET category = 'archive', updated_at = $1 WHERE id = $2",
            datetime.now(UTC),
            knowledge_id,
        )

    # -- Agent Definitions --

    async def upsert_agent_def(
        self,
        name: str,
        description: str,
        prompt_template: str,
        tools: list[str] | None = None,
        mcp_servers: list[str] | None = None,
        knowledge_areas: list[str] | None = None,
    ) -> None:
        await self._pool.execute(
            """INSERT INTO agent_defs
               (name, description, prompt_template, tools,
                mcp_servers, knowledge_areas, updated_at)
               VALUES ($1, $2, $3, $4, $5, $6, $7)
               ON CONFLICT (name) DO UPDATE SET
                 description = $2, prompt_template = $3,
                 tools = $4, mcp_servers = $5,
                 knowledge_areas = $6, updated_at = $7""",
            name,
            description,
            prompt_template,
            tools or [],
            mcp_servers or [],
            knowledge_areas or [],
            datetime.now(UTC),
        )

    async def get_agent_def(self, name: str) -> dict | None:
        row = await self._pool.fetchrow(
            "SELECT * FROM agent_defs WHERE name = $1", name
        )
        return dict(row) if row else None

    async def list_agent_defs(self) -> list[dict]:
        rows = await self._pool.fetch(
            "SELECT * FROM agent_defs ORDER BY name"
        )
        return [dict(r) for r in rows]

    async def delete_agent_def(self, name: str) -> None:
        await self._pool.execute(
            "DELETE FROM agent_defs WHERE name = $1", name
        )

    # -- Agent Shares --

    async def create_agent_share(self, agent_name: str, token: str) -> str:
        row = await self._pool.fetchrow(
            """INSERT INTO agent_shares (agent_name, token)
               VALUES ($1, $2) RETURNING id""",
            agent_name,
            token,
        )
        return row["id"]

    async def get_agent_share_by_token(self, token: str) -> dict | None:
        row = await self._pool.fetchrow(
            "SELECT * FROM agent_shares WHERE token = $1", token
        )
        return dict(row) if row else None

    async def get_agent_share(self, agent_name: str) -> dict | None:
        row = await self._pool.fetchrow(
            "SELECT * FROM agent_shares WHERE agent_name = $1", agent_name
        )
        return dict(row) if row else None

    async def delete_agent_share(self, agent_name: str) -> None:
        await self._pool.execute(
            "DELETE FROM agent_shares WHERE agent_name = $1", agent_name
        )

    # -- MCP Servers --

    async def upsert_mcp_server(self, name: str, url: str) -> None:
        await self._pool.execute(
            """INSERT INTO mcp_servers (name, url, updated_at)
               VALUES ($1, $2, $3)
               ON CONFLICT (name) DO UPDATE SET
                 url = $2, updated_at = $3""",
            name,
            url,
            datetime.now(UTC),
        )

    async def get_mcp_server(self, name: str) -> dict | None:
        row = await self._pool.fetchrow(
            "SELECT * FROM mcp_servers WHERE name = $1", name
        )
        return dict(row) if row else None

    async def list_mcp_servers(self) -> list[dict]:
        rows = await self._pool.fetch(
            "SELECT * FROM mcp_servers ORDER BY name"
        )
        return [dict(r) for r in rows]

    async def delete_mcp_server(self, name: str) -> None:
        await self._pool.execute(
            "DELETE FROM mcp_servers WHERE name = $1", name
        )

    # -- Users --

    async def get_or_create_user(self, email: str) -> dict:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM users WHERE email = $1", email
            )
            if row:
                return dict(row)

            user_id = uuid4().hex
            now = datetime.now(UTC)
            await conn.execute(
                """INSERT INTO users (id, email, created_at, updated_at)
                   VALUES ($1, $2, $3, $4)""",
                user_id,
                email,
                now,
                now,
            )
            return {
                "id": user_id,
                "email": email,
                "display_name": None,
                "created_at": now,
                "updated_at": now,
            }

    async def get_user(self, user_id: str) -> dict | None:
        row = await self._pool.fetchrow("SELECT * FROM users WHERE id = $1", user_id)
        return dict(row) if row else None

    async def update_user_display_name(self, user_id: str, display_name: str) -> None:
        await self._pool.execute(
            "UPDATE users SET display_name = $1, updated_at = $2 WHERE id = $3",
            display_name,
            datetime.now(UTC),
            user_id,
        )

    # -- Email Codes --

    async def create_email_code(self, email: str, code: str, expires_at: datetime) -> str:
        code_id = uuid4().hex
        await self._pool.execute(
            """INSERT INTO email_codes (id, email, code, expires_at, created_at)
               VALUES ($1, $2, $3, $4, $5)""",
            code_id,
            email,
            code,
            expires_at,
            datetime.now(UTC),
        )
        return code_id

    async def verify_email_code(self, email: str, code: str) -> bool:
        """Verify and consume an email code. Returns True if valid."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """SELECT id FROM email_codes
                   WHERE email = $1 AND code = $2
                     AND used = FALSE AND expires_at > $3
                   ORDER BY created_at DESC LIMIT 1""",
                email,
                code,
                datetime.now(UTC),
            )
            if not row:
                return False
            await conn.execute(
                "UPDATE email_codes SET used = TRUE WHERE id = $1",
                row["id"],
            )
            return True

    async def count_recent_codes(self, email: str, since: datetime) -> int:
        row = await self._pool.fetchrow(
            "SELECT COUNT(*) as cnt FROM email_codes WHERE email = $1 AND created_at > $2",
            email,
            since,
        )
        return row["cnt"] if row else 0

    # -- API Keys --

    async def create_api_key(
        self,
        name: str,
        key_hash: str,
        key_prefix: str,
        user_id: str | None = None,
    ) -> str:
        key_id = uuid4().hex
        await self._pool.execute(
            """INSERT INTO api_keys (id, user_id, name, key_hash, key_prefix, created_at)
               VALUES ($1, $2, $3, $4, $5, $6)""",
            key_id,
            user_id,
            name,
            key_hash,
            key_prefix,
            datetime.now(UTC),
        )
        return key_id

    async def get_api_key_by_hash(self, key_hash: str) -> dict | None:
        row = await self._pool.fetchrow(
            "SELECT * FROM api_keys WHERE key_hash = $1", key_hash
        )
        return dict(row) if row else None

    async def list_api_keys(self, user_id: str | None = None) -> list[dict]:
        cols = "id, user_id, name, key_prefix, created_at, last_used_at"
        if user_id:
            rows = await self._pool.fetch(
                f"SELECT {cols} FROM api_keys WHERE user_id = $1 ORDER BY created_at DESC",
                user_id,
            )
        else:
            rows = await self._pool.fetch(
                f"SELECT {cols} FROM api_keys ORDER BY created_at DESC"
            )
        return [dict(r) for r in rows]

    async def delete_api_key(self, key_id: str, user_id: str | None = None) -> bool:
        if user_id:
            result = await self._pool.execute(
                "DELETE FROM api_keys WHERE id = $1 AND user_id = $2", key_id, user_id
            )
        else:
            result = await self._pool.execute(
                "DELETE FROM api_keys WHERE id = $1", key_id
            )
        return result.split()[-1] != "0"

    async def touch_api_key(self, key_id: str) -> None:
        await self._pool.execute(
            "UPDATE api_keys SET last_used_at = $1 WHERE id = $2",
            datetime.now(UTC),
            key_id,
        )

