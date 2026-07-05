import time

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import require_api_key
from app.models.bot import Bot
from app.models.schemas import BotStats, SystemStats
from app.services.process_manager import process_manager
from app.services.system_stats import get_system_stats

router = APIRouter(prefix="/api/monitoring", tags=["monitoring"], dependencies=[Depends(require_api_key)])


@router.get("/system", response_model=SystemStats)
def system_stats(db: Session = Depends(get_db)):
    stats = get_system_stats()
    bots = db.query(Bot).all()
    online = sum(1 for b in bots if b.status == "running")
    offline = len(bots) - online
    return SystemStats(
        cpu_percent=stats["cpu_percent"],
        ram_percent=stats["ram_percent"],
        ram_used_mb=stats["ram_used_mb"],
        ram_total_mb=stats["ram_total_mb"],
        disk_percent=stats["disk_percent"],
        disk_used_gb=stats["disk_used_gb"],
        disk_total_gb=stats["disk_total_gb"],
        uptime_seconds=stats["server_uptime_seconds"],
        bots_online=online,
        bots_offline=offline,
    )


@router.get("/bots/{bot_id}", response_model=BotStats)
def bot_stats(bot_id: str, db: Session = Depends(get_db)):
    bot = db.query(Bot).filter(Bot.id == bot_id).first()
    if not bot:
        return BotStats(
            bot_id=bot_id, status="unknown", pid=None, cpu_percent=0, ram_mb=0,
            uptime_seconds=0, last_error="Bot não encontrado.",
        )
    bp = process_manager.get(bot_id)
    cpu, ram_mb = bp.resource_usage() if bp else (0.0, 0.0)
    uptime = bp.uptime_seconds() if bp else 0.0
    return BotStats(
        bot_id=bot_id,
        status=bot.status,
        pid=bp.pid if bp else None,
        cpu_percent=cpu,
        ram_mb=ram_mb,
        uptime_seconds=uptime,
        last_error=bot.last_error,
    )
