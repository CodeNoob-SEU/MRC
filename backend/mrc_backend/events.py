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
        self._history_excluded_types = {"preview"}
        self._coalesced_types = {"preview", "waveform", "status"}

    def bind_loop(self) -> None:
        self._loop = asyncio.get_running_loop()

    def publish(self, event_type: str, payload: Dict[str, Any]) -> None:
        event = {
            "type": event_type,
            "timestamp": datetime.now().isoformat(timespec="milliseconds"),
            "payload": payload,
        }
        if event_type not in self._history_excluded_types:
            self._history.append(event)
        if self._loop is None:
            return

        def enqueue() -> None:
            for client in list(self._clients):
                self._enqueue_latest(client, event)

        self._loop.call_soon_threadsafe(enqueue)

    async def subscribe(self) -> asyncio.Queue[Dict[str, Any]]:
        queue: asyncio.Queue[Dict[str, Any]] = asyncio.Queue(maxsize=64)
        self._clients.add(queue)
        for event in self._history:
            queue.put_nowait(event)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[Dict[str, Any]]) -> None:
        self._clients.discard(queue)

    def _enqueue_latest(self, queue: asyncio.Queue[Dict[str, Any]], event: Dict[str, Any]) -> None:
        event_type = str(event.get("type", ""))
        if event_type in self._coalesced_types:
            self._drop_queued_type(queue, event_type)

        while True:
            try:
                queue.put_nowait(event)
                return
            except asyncio.QueueFull:
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    return

    @staticmethod
    def _drop_queued_type(queue: asyncio.Queue[Dict[str, Any]], event_type: str) -> None:
        kept: Deque[Dict[str, Any]] = deque()
        while True:
            try:
                queued = queue.get_nowait()
            except asyncio.QueueEmpty:
                break
            if queued.get("type") != event_type:
                kept.append(queued)

        while kept:
            try:
                queue.put_nowait(kept.popleft())
            except asyncio.QueueFull:
                break
