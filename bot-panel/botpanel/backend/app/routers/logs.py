from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.security import require_api_key
from app.models.bot import Bot
from app.services.process_manager import process_manager

router = APIRouter(
    prefix="/api/bots/{bot_id}/logs", tags=["logs"], dependencies=[Depends(require_api_key)]
)


def _log_path(bot_id: str, db: Session):
    bot = db.query(Bot).filter(Bot.id == bot_id).first()
    if not bot:
        raise HTTPException(status_code=404, detail="Bot não encontrado.")
    folder = settings.bots_dir_path / bot.folder_name / "logs"
    folder.mkdir(parents=True, exist_ok=True)
    return folder / "output.log"


@router.get("")
def get_logs(bot_id: str, search: str = "", limit: int = 500, db: Session = Depends(get_db)):
    log_path = _log_path(bot_id, db)
    if not log_path.exists():
        return {"lines": []}
    lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
    if search:
        lines = [line for line in lines if search.lower() in line.lower()]
    return {"lines": lines[-limit:]}


@router.delete("")
def clear_logs(bot_id: str, db: Session = Depends(get_db)):
    log_path = _log_path(bot_id, db)
    log_path.write_text("", encoding="utf-8")
    bp = process_manager.get(bot_id)
    if bp:
        bp.log_buffer.clear()
    return {"ok": True}


@router.get("/download")
def download_logs(bot_id: str, db: Session = Depends(get_db)):
    log_path = _log_path(bot_id, db)
    if not log_path.exists():
        raise HTTPException(status_code=404, detail="Nenhum log encontrado.")
    return FileResponse(log_path, filename=f"{bot_id}-logs.txt")
