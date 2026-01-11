"""Lightweight per-session websocket broadcaster."""

from __future__ import annotations

import asyncio
import json
from typing import Dict, Set

from fastapi import WebSocket


class SessionBroadcaster:
    def __init__(self) -> None:
        self._connections: Dict[str, Set[WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, session_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._connections.setdefault(session_id, set()).add(websocket)

    async def disconnect(self, session_id: str, websocket: WebSocket) -> None:
        async with self._lock:
            peers = self._connections.get(session_id)
            if peers and websocket in peers:
                peers.remove(websocket)
            if peers is not None and not peers:
                self._connections.pop(session_id, None)

    async def broadcast_json(self, session_id: str, payload: dict) -> None:
        message = json.dumps(payload)
        async with self._lock:
            peers = list(self._connections.get(session_id, set()))
        if not peers:
            return
        stale = []
        for socket in peers:
            try:
                await socket.send_text(message)
            except Exception:
                stale.append(socket)
        if stale:
            async with self._lock:
                current_peers = self._connections.get(session_id)
                if current_peers:
                    for socket in stale:
                        current_peers.discard(socket)
                    if not current_peers:
                        self._connections.pop(session_id, None)


broadcaster = SessionBroadcaster()
