import datetime
import re

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.security import require_api_key
from app.models.bot import Bot, RestartLog
from app.models.schemas import BotCreate, BotOut, BotUpdate, RestartLogOut
from app.services.process_manager import process_manager

router = APIRouter(prefix="/api/bots", tags=["bots"], dependencies=[Depends(require_api_key)])


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9-_]+", "-", name.strip().lower()).strip("-")
    return slug or "bot"


async def _handle_crash(bot_id: str, db_factory) -> None:
    db = db_factory()
    try:
        bot = db.query(Bot).filter(Bot.id == bot_id).first()
        if not bot:
            return
        bp = process_manager.get(bot_id)
        bot.last_error = bp.last_error if bp else "O processo foi finalizado inesperadamente."
        if bot.auto_restart:
            bot.status = "running"
            db.add(RestartLog(bot_id=bot.id, reason="crash"))
            db.commit()
            folder = settings.bots_dir_path / bot.folder_name
            new_bp = process_manager.get_or_create(bot.id, folder, bot.start_command)
            await new_bp.start()
        else:
            bot.status = "crashed"
            db.commit()
    finally:
        db.close()


@router.on_event("startup")
async def _startup() -> None:
    from app.core.database import SessionLocal

    process_manager.start_monitor(lambda bot_id: _handle_crash(bot_id, SessionLocal))


@router.get("", response_model=list[BotOut])
def list_bots(db: Session = Depends(get_db)):
    return db.query(Bot).order_by(Bot.created_at.desc()).all()


@router.post("", response_model=BotOut, status_code=201)
def create_bot(payload: BotCreate, db: Session = Depends(get_db)):
    base_slug = _slugify(payload.name)
    slug = base_slug
    counter = 1
    while db.query(Bot).filter(Bot.folder_name == slug).first():
        counter += 1
        slug = f"{base_slug}-{counter}"

    bot = Bot(
        name=payload.name,
        description=payload.description,
        start_command=payload.start_command,
        folder_name=slug,
        runtime=payload.runtime,
        docker_image=payload.docker_image,
        auto_restart=payload.auto_restart,
        autostart_on_boot=payload.autostart_on_boot,
    )
    db.add(bot)
    db.commit()
    db.refresh(bot)

    folder = settings.bots_dir_path / bot.folder_name
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "logs").mkdir(exist_ok=True)
    return bot


@router.get("/{bot_id}", response_model=BotOut)
def get_bot(bot_id: str, db: Session = Depends(get_db)):
    bot = db.query(Bot).filter(Bot.id == bot_id).first()
    if not bot:
        raise HTTPException(status_code=404, detail="Bot não encontrado.")
    return bot


@router.patch("/{bot_id}", response_model=BotOut)
def update_bot(bot_id: str, payload: BotUpdate, db: Session = Depends(get_db)):
    bot = db.query(Bot).filter(Bot.id == bot_id).first()
    if not bot:
        raise HTTPException(status_code=404, detail="Bot não encontrado.")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(bot, field, value)
    db.commit()
    db.refresh(bot)
    return bot


@router.delete("/{bot_id}", status_code=204)
async def delete_bot(bot_id: str, db: Session = Depends(get_db)):
    bot = db.query(Bot).filter(Bot.id == bot_id).first()
    if not bot:
        raise HTTPException(status_code=404, detail="Bot não encontrado.")
    bp = process_manager.get(bot_id)
    if bp and bp.is_running:
        await bp.stop()
    process_manager.remove(bot_id)

    import shutil
    folder = settings.bots_dir_path / bot.folder_name
    if folder.exists():
        shutil.rmtree(folder)

    db.delete(bot)
    db.commit()


@router.post("/{bot_id}/start", response_model=BotOut)
async def start_bot(bot_id: str, db: Session = Depends(get_db)):
    bot = db.query(Bot).filter(Bot.id == bot_id).first()
    if not bot:
        raise HTTPException(status_code=404, detail="Bot não encontrado.")
    folder = settings.bots_dir_path / bot.folder_name
    bp = process_manager.get_or_create(bot.id, folder, bot.start_command)
    if bp.is_running:
        raise HTTPException(status_code=400, detail="O bot já está em execução.")
    await bp.start()
    bot.status = "running"
    bot.pid = bp.pid
    bot.last_started_at = datetime.datetime.utcnow()
    bot.last_error = ""
    db.add(RestartLog(bot_id=bot.id, reason="manual"))
    db.commit()
    db.refresh(bot)
    return bot


@router.post("/{bot_id}/stop", response_model=BotOut)
async def stop_bot(bot_id: str, db: Session = Depends(get_db)):
    bot = db.query(Bot).filter(Bot.id == bot_id).first()
    if not bot:
        raise HTTPException(status_code=404, detail="Bot não encontrado.")
    bp = process_manager.get(bot_id)
    if bp and bp.is_running:
        await bp.stop()
    bot.status = "stopped"
    bot.pid = None
    db.commit()
    db.refresh(bot)
    return bot


@router.post("/{bot_id}/restart", response_model=BotOut)
async def restart_bot(bot_id: str, db: Session = Depends(get_db)):
    bot = db.query(Bot).filter(Bot.id == bot_id).first()
    if not bot:
        raise HTTPException(status_code=404, detail="Bot não encontrado.")
    folder = settings.bots_dir_path / bot.folder_name
    bp = process_manager.get_or_create(bot.id, folder, bot.start_command)
    if bp.is_running:
        await bp.stop()
    await bp.start()
    bot.status = "running"
    bot.pid = bp.pid
    bot.last_started_at = datetime.datetime.utcnow()
    bot.last_error = ""
    db.add(RestartLog(bot_id=bot.id, reason="manual"))
    db.commit()
    db.refresh(bot)
    return bot


@router.get("/{bot_id}/restarts", response_model=list[RestartLogOut])
def list_restarts(bot_id: str, db: Session = Depends(get_db)):
    return (
        db.query(RestartLog)
        .filter(RestartLog.bot_id == bot_id)
        .order_by(RestartLog.timestamp.desc())
        .limit(100)
        .all()
    )
