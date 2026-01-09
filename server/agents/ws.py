from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status
from typing import Optional

from ..auth import decode_access_token
from .. import db
from ..realtime import broadcaster

router = APIRouter()


def _validate_token(token: Optional[str]):
    if not token:
        return None
    payload = decode_access_token(token)
    if not payload or 'sub' not in payload:
        return None
    return db.get_user_by_identifier(payload['sub'])


@router.websocket('/ws/sessions/{session_id}')
async def session_socket(websocket: WebSocket, session_id: str, token: Optional[str] = None):
    user = _validate_token(token)
    if not user:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    await broadcaster.connect(session_id, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        await broadcaster.disconnect(session_id, websocket)
