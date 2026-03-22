"""iMessage gateway — FSEvents watcher + AppleScript sender."""

import asyncio
import logging
import sqlite3
from pathlib import Path

from crow.config.settings import Settings
from crow.events.bus import EventBus
from crow.events.types import MESSAGE_INBOUND, MESSAGE_RESPONSE, Event
from crow.gateways.base import Gateway
from crow.gateways.imessage.watcher import start_watcher

logger = logging.getLogger(__name__)


class IMessageGateway(Gateway):
    name = "imessage"

    def __init__(self, settings: Settings):
        self.chat_db_path = Path(settings.imessage_chat_db).expanduser()
        self.allowed_numbers = set(settings.imessage_allowed_numbers)
        self._last_rowid: int = 0
        self._observer = None
        self._bus: EventBus | None = None

    async def start(self, bus: EventBus) -> None:
        self._bus = bus
        bus.subscribe(MESSAGE_RESPONSE, self._on_response)

        # Get current max rowid so we don't process old messages
        self._last_rowid = self._get_max_rowid()

        loop = asyncio.get_running_loop()
        self._observer = start_watcher(
            str(self.chat_db_path.parent),
            self._process_new_messages,
            loop,
        )
        logger.info("iMessage gateway started, last_rowid=%d", self._last_rowid)

    async def stop(self) -> None:
        if self._observer:
            self._observer.stop()
            self._observer.join()

    async def send(self, gateway_thread_id: str, text: str) -> None:
        """Send via AppleScript."""
        # Escape for AppleScript
        escaped = text.replace("\\", "\\\\").replace('"', '\\"')
        script = (
            'tell application "Messages"\n'
            "  set targetService to 1st account whose service type = iMessage\n"
            f'  set targetBuddy to participant "{gateway_thread_id}" of targetService\n'
            f'  send "{escaped}" to targetBuddy\n'
            "end tell"
        )
        proc = await asyncio.create_subprocess_exec(
            "osascript", "-e", script,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0:
            logger.error("AppleScript send failed: %s", stderr.decode())

    def _get_max_rowid(self) -> int:
        try:
            conn = sqlite3.connect(f"file:{self.chat_db_path}?mode=ro", uri=True)
            row = conn.execute("SELECT MAX(ROWID) FROM message").fetchone()
            conn.close()
            return row[0] or 0
        except Exception:
            logger.exception("Failed to read chat.db max rowid")
            return 0

    async def _process_new_messages(self) -> None:
        """Query chat.db for messages newer than last_rowid."""
        if not self._bus:
            return

        try:
            conn = sqlite3.connect(f"file:{self.chat_db_path}?mode=ro", uri=True)
            conn.row_factory = sqlite3.Row

            rows = conn.execute(
                """
                SELECT m.ROWID, m.text, m.is_from_me, h.id as handle_id
                FROM message m
                LEFT JOIN handle h ON m.handle_id = h.ROWID
                WHERE m.ROWID > ? AND m.is_from_me = 0 AND m.text IS NOT NULL
                ORDER BY m.ROWID ASC
                """,
                (self._last_rowid,),
            ).fetchall()

            for row in rows:
                handle = row["handle_id"] or ""
                self._last_rowid = max(self._last_rowid, row["ROWID"])

                # Filter by allowed numbers
                if self.allowed_numbers and handle not in self.allowed_numbers:
                    logger.debug("Ignoring message from %s (not in allowlist)", handle)
                    continue

                logger.info("New iMessage from %s: %s", handle, row["text"][:50])
                await self._bus.publish(
                    Event(
                        type=MESSAGE_INBOUND,
                        data={
                            "gateway": "imessage",
                            "gateway_thread_id": handle,
                            "text": row["text"],
                        },
                    )
                )

            conn.close()
        except Exception:
            logger.exception("Failed to process new iMessages")

    async def _on_response(self, event: Event) -> None:
        """Send response back via iMessage if it came from this gateway."""
        if event.data.get("gateway") != "imessage":
            return
        await self.send(event.data["gateway_thread_id"], event.data["text"])
