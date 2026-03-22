"""FSEvents watcher for iMessage chat.db changes."""

import asyncio
import logging
from collections.abc import Callable, Coroutine
from typing import Any

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

logger = logging.getLogger(__name__)


class ChatDBHandler(FileSystemEventHandler):
    """Fires callback when chat.db or its WAL file changes."""

    def __init__(
        self,
        callback: Callable[[], Coroutine[Any, Any, None]],
        loop: asyncio.AbstractEventLoop,
    ):
        self._callback = callback
        self._loop = loop

    def on_modified(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return
        src = str(event.src_path)
        if "chat.db" in src:
            asyncio.run_coroutine_threadsafe(self._callback(), self._loop)


def start_watcher(
    watch_dir: str,
    callback: Callable[[], Coroutine[Any, Any, None]],
    loop: asyncio.AbstractEventLoop,
) -> Observer:
    """Start a watchdog observer on the Messages directory."""
    handler = ChatDBHandler(callback, loop)
    observer = Observer()
    observer.schedule(handler, watch_dir, recursive=False)
    observer.start()
    logger.info("iMessage watcher started on %s", watch_dir)
    return observer
