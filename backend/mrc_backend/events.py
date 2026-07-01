from __future__ import annotations

import asyncio
from collections import deque
from datetime import datetime
from typing import Any, Deque, Dict, Optional, Set


class EventBus:
    def __init__(self, history_limit: int = 200) -> None:
        self._clients: Set[asyncio.Queue[Dict[str, Any]]] = set()
        self._history: Deque[Dict[str, Any]] = deque(maxlen=history_limit)
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    def bind_loop(self) -> None:
        self._loop = asyncio.get_running_loop()

    def publish(self, event_type: str, payload: Dict[str, Any]) -> None:
        event = {
            "type": event_type,
            "timestamp": datetime.now().isoformat(timespec="milliseconds"),
            "payload": payload,
        }
        self._history.append(event)
        if self._loop is None:
            return

        def enqueue() -> None:
            for client in list(self._clients):
                client.put_nowait(event)

        self._loop.call_soon_threadsafe(enqueue)

    async def subscribe(self) -> asyncio.Queue[Dict[str, Any]]:
        queue: asyncio.Queue[Dict[str, Any]] = asyncio.Queue()
        self._clients.add(queue)
        for event in self._history:
            queue.put_nowait(event)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[Dict[str, Any]]) -> None:
        self._clients.discard(queue)
