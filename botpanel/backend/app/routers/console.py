import asyncio
import hmac

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from app.core.config import settings
from app.services.process_manager import process_manager

router = APIRouter(prefix="/api/bots", tags=["console"])


@router.websocket("/{bot_id}/console")
async def bot_console(websocket: WebSocket, bot_id: str, api_key: str = Query(default="")):
    # WebSockets do navegador não suportam headers customizados, então a
    # chave de API é passada como query param aqui. Ainda assim, é a mesma
    # PANEL_API_KEY e a conexão é recusada sem ela.
    if not api_key or not hmac.compare_digest(api_key, settings.PANEL_API_KEY):
        await websocket.close(code=4401)
        return

    await websocket.accept()
    bp = process_manager.get(bot_id)

    # envia o histórico de logs já existente
    if bp:
        for line in list(bp.log_buffer):
            await websocket.send_text(line)

    queue: asyncio.Queue = asyncio.Queue()
    if bp:
        bp.subscribers.add(queue)

    try:
        while True:
            line = await queue.get()
            await websocket.send_text(line)
    except WebSocketDisconnect:
        pass
    finally:
        if bp:
            bp.subscribers.discard(queue)
