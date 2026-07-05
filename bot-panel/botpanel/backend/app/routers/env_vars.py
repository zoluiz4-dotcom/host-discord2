from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.security import require_api_key
from app.models.bot import Bot
from app.models.schemas import EnvVarsIn, EnvVarsOut
from app.services.process_manager import process_manager

router = APIRouter(
    prefix="/api/bots/{bot_id}/env", tags=["env"], dependencies=[Depends(require_api_key)]
)


def _env_path(bot_id: str, db: Session):
    bot = db.query(Bot).filter(Bot.id == bot_id).first()
    if not bot:
        raise HTTPException(status_code=404, detail="Bot não encontrado.")
    folder = settings.bots_dir_path / bot.folder_name
    folder.mkdir(parents=True, exist_ok=True)
    return bot, folder / ".env"


def _parse_env(text: str) -> dict[str, str]:
    variables: dict[str, str] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        variables[key.strip()] = value.strip()
    return variables


def _serialize_env(variables: dict[str, str]) -> str:
    return "\n".join(f"{key}={value}" for key, value in variables.items()) + "\n"


@router.get("", response_model=EnvVarsOut)
def get_env(bot_id: str, reveal: bool = False, db: Session = Depends(get_db)):
    _, env_path = _env_path(bot_id, db)
    if not env_path.exists():
        return EnvVarsOut(variables={})
    variables = _parse_env(env_path.read_text(encoding="utf-8"))
    if not reveal:
        variables = {key: "••••••••" for key in variables}
    return EnvVarsOut(variables=variables)


@router.put("")
async def update_env(bot_id: str, payload: EnvVarsIn, db: Session = Depends(get_db)):
    bot, env_path = _env_path(bot_id, db)
    env_path.write_text(_serialize_env(payload.variables), encoding="utf-8")

    if payload.restart_bot:
        bp = process_manager.get(bot_id)
        if bp and bp.is_running:
            await bp.stop()
            await bp.start()
            bot.status = "running"
            bot.pid = bp.pid
            db.commit()

    return {"ok": True}
