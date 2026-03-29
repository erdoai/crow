import json
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

    async def set_conversation_title(
        self, conversation_id: str, title: str
    ) -> None:
        await self._pool.execute(
            "UPDATE conversations SET title = $1 WHERE id = $2",
            title,
            conversation_id,
        )

    async def list_conversations(
        self,
        limit: int = 50,
        user_id: str | None = None,
        exclude_delegates: bool = False,
    ) -> list[dict]:
        conditions = []
        params: list = []
        idx = 1

        if user_id:
            conditions.append(f"user_id = ${idx}")
            params.append(user_id)
            idx += 1

        if exclude_delegates:
            conditions.append(f"gateway_thread_id NOT LIKE ${idx}")
            params.append("delegate-%")
            idx += 1
            conditions.append(f"gateway != ${idx}")
            params.append("background")
            idx += 1

        where = f" WHERE {' AND '.join(conditions)}" if conditions else ""
        params.append(limit)
        query = f"SELECT * FROM conversations{where} ORDER BY updated_at DESC LIMIT ${idx}"
        rows = await self._pool.fetch(query, *params)
        return [dict(r) for r in rows]

    # -- Messages --

    async def insert_message(
        self,
        conversation_id: str,
        role: str,
        content: str | list,
        agent_name: str | None = None,
    ) -> str:
        msg_id = uuid4().hex
        # JSONB column: lists are stored as JSON arrays, strings as JSON strings
        content_json = json.dumps(content)
        await self._pool.execute(
            """INSERT INTO messages (id, conversation_id, role, content, agent_name, created_at)
               VALUES ($1, $2, $3, $4::jsonb, $5, $6)""",
            msg_id,
            conversation_id,
            role,
            content_json,
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
               ORDER BY seq ASC, created_at ASC
               LIMIT $2""",
            conversation_id,
            limit,
        )
        return [dict(r) for r in rows]

    # -- Jobs --

    async def last_agent_for_conversation(self, conversation_id: str) -> str | None:
        """Return the agent_name from the most recent job in a conversation."""
        row = await self._pool.fetchrow(
            """SELECT agent_name FROM jobs
               WHERE conversation_id = $1
               ORDER BY created_at DESC LIMIT 1""",
            conversation_id,
        )
        return row["agent_name"] if row else None

    async def create_job(
        self,
        agent_name: str,
        input_text: str,
        conversation_id: str | None = None,
        source: str = "message",
        mode: str = "chat",
        parent_conversation_id: str | None = None,
    ) -> str:
        job_id = uuid4().hex
        await self._pool.execute(
            """INSERT INTO jobs
               (id, agent_name, conversation_id, status,
                input, source, mode, parent_conversation_id, created_at)
               VALUES ($1, $2, $3, 'pending', $4, $5, $6, $7, $8)""",
            job_id,
            agent_name,
            conversation_id,
            input_text,
            source,
            mode,
            parent_conversation_id,
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
        output: str | list,
        tokens_used: int = 0,
    ) -> None:
        output_str = json.dumps(output) if isinstance(output, list) else output
        await self._pool.execute(
            """UPDATE jobs
               SET status = 'completed', output = $1, tokens_used = $2, completed_at = $3
               WHERE id = $4""",
            output_str,
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

    async def requeue_job(self, job_id: str) -> None:
        """Move a running job back to pending for another worker to pick up."""
        await self._pool.execute(
            """UPDATE jobs
               SET status = 'pending', worker_id = NULL,
                   started_at = NULL, attempt = attempt + 1
               WHERE id = $1 AND status = 'running'""",
            job_id,
        )

    async def get_job(self, job_id: str, user_id: str | None = None) -> dict | None:
        if user_id:
            row = await self._pool.fetchrow(
                """SELECT j.* FROM jobs j
                   JOIN conversations c ON j.conversation_id = c.id
                   WHERE j.id = $1 AND c.user_id = $2""",
                job_id,
                user_id,
            )
        else:
            row = await self._pool.fetchrow(
                "SELECT * FROM jobs WHERE id = $1", job_id
            )
        return dict(row) if row else None

    async def list_jobs(
        self,
        status: str | None = None,
        source: str | None = None,
        limit: int = 50,
        user_id: str | None = None,
    ) -> list[dict]:
        conditions = []
        params: list = []
        idx = 1
        join = ""

        if user_id:
            join = " JOIN conversations c ON j.conversation_id = c.id"
            conditions.append(f"c.user_id = ${idx}")
            params.append(user_id)
            idx += 1

        if status:
            conditions.append(f"j.status = ${idx}")
            params.append(status)
            idx += 1

        if source:
            conditions.append(f"j.source = ${idx}")
            params.append(source)
            idx += 1

        where = f" WHERE {' AND '.join(conditions)}" if conditions else ""
        params.append(limit)
        query = f"SELECT j.* FROM jobs j{join}{where} ORDER BY j.created_at DESC LIMIT ${idx}"
        rows = await self._pool.fetch(query, *params)
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

        cols = "id, agent_name, category, title, content"
        cols += ", source_type, source_ref, tags, created_at, updated_at"
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
        source_type: str | None = None,
        source_ref: str | None = None,
        tags: list[str] | None = None,
        embedding: list[float] | None = None,
        user_id: str | None = None,
    ) -> str:
        knowledge_id = uuid4().hex
        now = datetime.now(UTC)
        verified_at = now if source_ref else None
        if embedding:
            await self._pool.execute(
                """INSERT INTO knowledge
                   (id, agent_name, category, title, content,
                    source_type, source_ref, source_verified_at,
                    tags, embedding, user_id, created_at, updated_at)
                   VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)""",
                knowledge_id,
                agent_name,
                category,
                title,
                content,
                source_type,
                source_ref,
                verified_at,
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
                    source_type, source_ref, source_verified_at,
                    tags, user_id, created_at, updated_at)
                   VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)""",
                knowledge_id,
                agent_name,
                category,
                title,
                content,
                source_type,
                source_ref,
                verified_at,
                tags or [],
                user_id,
                now,
                now,
            )
        return knowledge_id

    async def archive_knowledge(self, knowledge_id: str, user_id: str | None = None) -> None:
        if user_id:
            await self._pool.execute(
                "UPDATE knowledge SET category = 'archive', updated_at = $1"
                " WHERE id = $2 AND user_id = $3",
                datetime.now(UTC),
                knowledge_id,
                user_id,
            )
        else:
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
        user_id: str | None = None,
        parent_agent: str | None = None,
        max_iterations: int | None = None,
        mcp_configs: dict | None = None,
        mode: str = "chat",
    ) -> None:
        import json as _json

        now = datetime.now(UTC)
        mcp_configs_json = _json.dumps(mcp_configs) if mcp_configs else None
        # Delete existing then insert (handles NULL user_id correctly)
        if user_id:
            await self._pool.execute(
                "DELETE FROM agent_defs WHERE name = $1 AND user_id = $2", name, user_id
            )
        else:
            await self._pool.execute(
                "DELETE FROM agent_defs WHERE name = $1 AND user_id IS NULL", name
            )
        await self._pool.execute(
            """INSERT INTO agent_defs
               (name, description, prompt_template, tools,
                mcp_servers, knowledge_areas, user_id,
                parent_agent, max_iterations, mcp_configs,
                mode, updated_at)
               VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9,
                       $10::jsonb, $11, $12)""",
            name, description, prompt_template,
            tools or [], mcp_servers or [], knowledge_areas or [],
            user_id, parent_agent, max_iterations, mcp_configs_json,
            mode, now,
        )

    async def get_agent_def(self, name: str, user_id: str | None = None) -> dict | None:
        """Get agent by name. Checks user's own first, then instance-level."""
        if user_id:
            row = await self._pool.fetchrow(
                "SELECT * FROM agent_defs WHERE name = $1 AND user_id = $2", name, user_id
            )
            if row:
                return dict(row)
        row = await self._pool.fetchrow(
            "SELECT * FROM agent_defs WHERE name = $1 AND user_id IS NULL", name
        )
        return dict(row) if row else None

    async def list_agent_defs(
        self, user_id: str | None = None,
        parent: str | None = None, include_all: bool = False,
    ) -> list[dict]:
        """List agents visible to a user.

        Default: top-level only (parent IS NULL), user's own + instance-level.
        parent="trading": sub-agents of trading.
        include_all=True: everything.
        """
        conditions = []
        params = []
        idx = 1

        # User scoping: own + instance-level
        if user_id:
            conditions.append(f"(user_id IS NULL OR user_id = ${idx})")
            params.append(user_id)
            idx += 1
        else:
            conditions.append("user_id IS NULL")

        # Parent filtering
        if not include_all:
            if parent:
                conditions.append(f"parent_agent = ${idx}")
                params.append(parent)
                idx += 1
            else:
                conditions.append("parent_agent IS NULL")

        where = " AND ".join(conditions)
        rows = await self._pool.fetch(
            f"SELECT * FROM agent_defs WHERE {where} ORDER BY name", *params
        )
        return [dict(r) for r in rows]

    async def list_sub_agents(self, parent_name: str, user_id: str | None = None) -> list[dict]:
        """List sub-agents of a specific parent."""
        return await self.list_agent_defs(user_id=user_id, parent=parent_name)

    async def delete_agent_def(self, name: str, user_id: str | None = None) -> None:
        if user_id:
            await self._pool.execute(
                "DELETE FROM agent_defs WHERE name = $1 AND user_id = $2", name, user_id
            )
        else:
            await self._pool.execute(
                "DELETE FROM agent_defs WHERE name = $1 AND user_id IS NULL", name
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

    async def upsert_mcp_server(
        self, name: str, url: str, headers: dict | None = None
    ) -> None:
        import json

        headers_json = json.dumps(headers or {})
        await self._pool.execute(
            """INSERT INTO mcp_servers (name, url, headers, updated_at)
               VALUES ($1, $2, $3::jsonb, $4)
               ON CONFLICT (name) DO UPDATE SET
                 url = $2, headers = $3::jsonb, updated_at = $4""",
            name,
            url,
            headers_json,
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

    # -- State Channel --

    async def set_state(
        self, key: str, data: dict, user_id: str | None = None
    ) -> dict:
        import json

        data_json = json.dumps(data)
        row = await self._pool.fetchrow(
            """INSERT INTO state (key, user_id, data, updated_at)
               VALUES ($1, $2, $3::jsonb, NOW())
               ON CONFLICT (key, user_id) DO UPDATE SET
                 data = $3::jsonb, updated_at = NOW()
               RETURNING *""",
            key,
            user_id or "",
            data_json,
        )
        return dict(row)

    async def get_state(
        self, key: str, user_id: str | None = None
    ) -> dict | None:
        row = await self._pool.fetchrow(
            "SELECT * FROM state WHERE key = $1 AND user_id = $2",
            key,
            user_id or "",
        )
        return dict(row) if row else None

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

    # -- Dashboard Views --

    async def upsert_dashboard_view(
        self, name: str, label: str, files: dict[str, str],
        user_id: str | None = None,
    ) -> None:
        import json

        files_json = json.dumps(files)
        now = datetime.now(UTC)
        # Delete existing then insert (handles NULL user_id correctly)
        if user_id:
            await self._pool.execute(
                "DELETE FROM dashboard_views WHERE name = $1 AND user_id = $2", name, user_id
            )
        else:
            await self._pool.execute(
                "DELETE FROM dashboard_views WHERE name = $1 AND user_id IS NULL", name
            )
        await self._pool.execute(
            """INSERT INTO dashboard_views (name, label, files, user_id, created_at, updated_at)
               VALUES ($1, $2, $3::jsonb, $4, $5, $6)""",
            name, label, files_json, user_id, now, now,
        )

    async def get_dashboard_view(self, name: str, user_id: str | None = None) -> dict | None:
        """Get a dashboard view. Returns user's own view first, then instance-level."""
        if user_id:
            row = await self._pool.fetchrow(
                "SELECT * FROM dashboard_views WHERE name = $1 AND user_id = $2", name, user_id
            )
            if row:
                return dict(row)
        # Fall back to instance-level
        row = await self._pool.fetchrow(
            "SELECT * FROM dashboard_views WHERE name = $1 AND user_id IS NULL", name
        )
        return dict(row) if row else None

    async def get_dashboard_view_by_token(self, token: str) -> dict | None:
        row = await self._pool.fetchrow(
            "SELECT * FROM dashboard_views WHERE share_token = $1", token
        )
        return dict(row) if row else None

    async def list_dashboard_views(self, user_id: str | None = None) -> list[dict]:
        """List views visible to a user: their own + instance-level."""
        rows = await self._pool.fetch(
            "SELECT name, label, user_id, share_token, created_at, updated_at "
            "FROM dashboard_views WHERE user_id IS NULL OR user_id = $1 ORDER BY name",
            user_id,
        )
        return [dict(r) for r in rows]

    async def delete_dashboard_view(self, name: str, user_id: str | None = None) -> bool:
        if user_id:
            result = await self._pool.execute(
                "DELETE FROM dashboard_views WHERE name = $1 AND user_id = $2", name, user_id
            )
        else:
            result = await self._pool.execute(
                "DELETE FROM dashboard_views WHERE name = $1 AND user_id IS NULL", name
            )
        return result.split()[-1] != "0"

    async def set_dashboard_share_token(self, name: str, user_id: str, token: str) -> None:
        await self._pool.execute(
            "UPDATE dashboard_views SET share_token = $1 WHERE name = $2 AND user_id = $3",
            token, name, user_id,
        )

    async def remove_dashboard_share_token(self, name: str, user_id: str) -> None:
        await self._pool.execute(
            "UPDATE dashboard_views SET share_token = NULL WHERE name = $1 AND user_id = $2",
            name, user_id,
        )

    # -- Attachments --

    async def insert_attachment(
        self,
        message_id: str,
        filename: str,
        content_type: str,
        size_bytes: int,
        data: str,
    ) -> str:
        att_id = uuid4().hex
        await self._pool.execute(
            """INSERT INTO attachments
               (id, message_id, filename, content_type,
                size_bytes, data, created_at)
               VALUES ($1, $2, $3, $4, $5, $6, $7)""",
            att_id, message_id, filename, content_type,
            size_bytes, data, datetime.now(UTC),
        )
        return att_id

    async def insert_attachment_for_job(
        self,
        job_id: str,
        filename: str,
        content_type: str,
        size_bytes: int,
        data: str,
    ) -> str:
        att_id = uuid4().hex
        await self._pool.execute(
            """INSERT INTO attachments
               (id, job_id, filename, content_type,
                size_bytes, data, created_at)
               VALUES ($1, $2, $3, $4, $5, $6, $7)""",
            att_id, job_id, filename, content_type,
            size_bytes, data, datetime.now(UTC),
        )
        return att_id

    async def get_attachment(self, attachment_id: str) -> dict | None:
        row = await self._pool.fetchrow(
            "SELECT * FROM attachments WHERE id = $1", attachment_id
        )
        return dict(row) if row else None

    async def get_attachments_for_messages(self, message_ids: list[str]) -> dict[str, list[dict]]:
        """Batch fetch attachments for multiple messages. Returns {message_id: [attachments]}."""
        if not message_ids:
            return {}
        rows = await self._pool.fetch(
            "SELECT * FROM attachments WHERE message_id = ANY($1)",
            message_ids,
        )
        result: dict[str, list[dict]] = {}
        for row in rows:
            r = dict(row)
            mid = r["message_id"]
            result.setdefault(mid, []).append(r)
        return result

    async def link_job_attachments_to_message(self, job_id: str, message_id: str) -> None:
        await self._pool.execute(
            "UPDATE attachments SET message_id = $1, job_id = NULL WHERE job_id = $2",
            message_id, job_id,
        )

    # -- Scheduled Jobs --

    async def cancel_active_schedules(
        self,
        agent_name: str,
        conversation_id: str | None = None,
    ) -> int:
        """Cancel all active schedules for an agent+conversation pair."""
        if conversation_id:
            result = await self._pool.execute(
                """UPDATE scheduled_jobs SET status = 'completed'
                   WHERE agent_name = $1 AND conversation_id = $2
                     AND status = 'active'""",
                agent_name,
                conversation_id,
            )
        else:
            result = await self._pool.execute(
                """UPDATE scheduled_jobs SET status = 'completed'
                   WHERE agent_name = $1 AND conversation_id IS NULL
                     AND status = 'active'""",
                agent_name,
            )
        return int(result.split()[-1])

    async def create_scheduled_job(
        self,
        scheduled_id: str,
        agent_name: str,
        input_text: str,
        run_at: datetime,
        cron: str | None = None,
        conversation_id: str | None = None,
        user_id: str | None = None,
        created_by_job_id: str | None = None,
    ) -> dict:
        await self._pool.execute(
            """INSERT INTO scheduled_jobs
               (id, agent_name, input, conversation_id, user_id, cron, run_at,
                status, created_by_job_id, created_at)
               VALUES ($1, $2, $3, $4, $5, $6, $7, 'active', $8, $9)""",
            scheduled_id,
            agent_name,
            input_text,
            conversation_id,
            user_id,
            cron,
            run_at,
            created_by_job_id,
            datetime.now(UTC),
        )
        return {
            "id": scheduled_id,
            "agent_name": agent_name,
            "input": input_text,
            "cron": cron,
            "run_at": run_at.isoformat(),
            "status": "active",
        }

    async def get_due_scheduled_jobs(self, limit: int = 50) -> list[dict]:
        """Atomically fetch and lock due scheduled jobs."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """SELECT * FROM scheduled_jobs
                   WHERE status = 'active' AND run_at <= $1
                   ORDER BY run_at ASC
                   LIMIT $2
                   FOR UPDATE SKIP LOCKED""",
                datetime.now(UTC),
                limit,
            )
            return [dict(r) for r in rows]

    async def advance_scheduled_job(
        self, scheduled_id: str, next_run_at: datetime | None
    ) -> None:
        if next_run_at:
            await self._pool.execute(
                "UPDATE scheduled_jobs SET run_at = $1 WHERE id = $2",
                next_run_at,
                scheduled_id,
            )
        else:
            await self._pool.execute(
                "UPDATE scheduled_jobs SET status = 'completed' WHERE id = $1",
                scheduled_id,
            )

    async def list_scheduled_jobs(
        self, user_id: str | None = None, limit: int = 50
    ) -> list[dict]:
        if user_id:
            rows = await self._pool.fetch(
                """SELECT * FROM scheduled_jobs
                   WHERE user_id = $1 OR user_id IS NULL
                   ORDER BY created_at DESC LIMIT $2""",
                user_id,
                limit,
            )
        else:
            rows = await self._pool.fetch(
                "SELECT * FROM scheduled_jobs ORDER BY created_at DESC LIMIT $1",
                limit,
            )
        return [dict(r) for r in rows]

    async def cancel_scheduled_job(
        self, scheduled_id: str, user_id: str | None = None
    ) -> bool:
        if user_id:
            result = await self._pool.execute(
                """UPDATE scheduled_jobs SET status = 'completed'
                   WHERE id = $1 AND user_id = $2 AND status = 'active'""",
                scheduled_id,
                user_id,
            )
        else:
            result = await self._pool.execute(
                """UPDATE scheduled_jobs SET status = 'completed'
                   WHERE id = $1 AND status = 'active'""",
                scheduled_id,
            )
        return result.split()[-1] != "0"

    # -- Device Tokens (Push Notifications) --

    async def register_device_token(
        self, user_id: str, token: str, platform: str = "apns"
    ) -> dict:
        row_id = uuid4().hex
        await self._pool.execute(
            """INSERT INTO device_tokens (id, user_id, token, platform)
               VALUES ($1, $2, $3, $4)
               ON CONFLICT (token) DO UPDATE SET user_id = $2, platform = $4""",
            row_id,
            user_id,
            token,
            platform,
        )
        return {"id": row_id, "token": token, "platform": platform}

    async def unregister_device_token(self, token: str) -> bool:
        result = await self._pool.execute(
            "DELETE FROM device_tokens WHERE token = $1", token
        )
        return result.split()[-1] != "0"

    async def get_device_tokens_for_user(self, user_id: str) -> list[dict]:
        rows = await self._pool.fetch(
            "SELECT token, platform FROM device_tokens WHERE user_id = $1",
            user_id,
        )
        return [dict(r) for r in rows]

    # -- Zombie Job Reaping --

    async def requeue_zombie_jobs(
        self, cutoff, max_attempts: int = 3
    ) -> tuple[list[dict], list[dict]]:
        """Requeue zombie jobs under retry cap, fail the rest.

        Returns (requeued, failed) lists.
        """
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                requeued = await conn.fetch(
                    """UPDATE jobs
                       SET status = 'pending', worker_id = NULL,
                           started_at = NULL, attempt = attempt + 1
                       WHERE status = 'running'
                         AND started_at < $1
                         AND attempt < $2
                       RETURNING id, agent_name, started_at, conversation_id, attempt""",
                    cutoff,
                    max_attempts,
                )
                failed = await conn.fetch(
                    """UPDATE jobs
                       SET status = 'failed',
                           error = 'Exceeded max retry attempts',
                           completed_at = now()
                       WHERE status = 'running'
                         AND started_at < $1
                         AND attempt >= $2
                       RETURNING id, agent_name, started_at, conversation_id, attempt""",
                    cutoff,
                    max_attempts,
                )
        return [dict(r) for r in requeued], [dict(r) for r in failed]

    # -- Agent Store (Persistent Structured KV) --

    async def store_get(
        self, namespace: str, key: str, user_id: str | None = None
    ) -> dict | None:
        uid = user_id or ""
        row = await self._pool.fetchrow(
            """SELECT data, created_at, updated_at FROM agent_store
               WHERE namespace = $1 AND key = $2
                 AND (user_id = $3 OR user_id = '')
               ORDER BY CASE WHEN user_id = $3 THEN 0 ELSE 1 END
               LIMIT 1""",
            namespace,
            key,
            uid,
        )
        return dict(row) if row else None

    async def store_set(
        self, namespace: str, key: str, data: dict, user_id: str | None = None
    ) -> dict:
        import json

        data_json = json.dumps(data)
        row = await self._pool.fetchrow(
            """INSERT INTO agent_store (namespace, key, user_id, data)
               VALUES ($1, $2, $3, $4::jsonb)
               ON CONFLICT (namespace, key, user_id)
               DO UPDATE SET data = $4::jsonb, updated_at = NOW()
               RETURNING *""",
            namespace,
            key,
            user_id or "",
            data_json,
        )
        return dict(row)

    async def store_update(
        self,
        namespace: str,
        key: str,
        path: str,
        value,
        user_id: str | None = None,
    ) -> dict | None:
        import json

        # Convert dot-notation path to Postgres array: "a.0.b" -> "{a,0,b}"
        pg_path = "{" + path.replace(".", ",") + "}"
        value_json = json.dumps(value)
        row = await self._pool.fetchrow(
            """UPDATE agent_store
               SET data = jsonb_set(data, $4::text[], $5::jsonb, true),
                   updated_at = NOW()
               WHERE namespace = $1 AND key = $2 AND user_id = $3
               RETURNING *""",
            namespace,
            key,
            user_id or "",
            pg_path,
            value_json,
        )
        return dict(row) if row else None

    async def store_delete(
        self, namespace: str, key: str, user_id: str | None = None
    ) -> bool:
        uid = user_id or ""
        result = await self._pool.execute(
            """DELETE FROM agent_store
               WHERE namespace = $1 AND key = $2
                 AND (user_id = $3 OR user_id = '')""",
            namespace,
            key,
            uid,
        )
        return result.split()[-1] != "0"

    async def store_namespaces(self, user_id: str | None = None) -> list[dict]:
        uid = user_id or ""
        rows = await self._pool.fetch(
            """SELECT namespace, COUNT(*) AS key_count,
                      MAX(updated_at) AS updated_at
               FROM agent_store WHERE user_id = $1 OR user_id = ''
               GROUP BY namespace ORDER BY MAX(updated_at) DESC""",
            uid,
        )
        return [dict(r) for r in rows]

    async def store_list(
        self, namespace: str, user_id: str | None = None
    ) -> list[dict]:
        uid = user_id or ""
        rows = await self._pool.fetch(
            """SELECT key, updated_at FROM agent_store
               WHERE namespace = $1 AND (user_id = $2 OR user_id = '')
               ORDER BY updated_at DESC""",
            namespace,
            uid,
        )
        return [dict(r) for r in rows]

