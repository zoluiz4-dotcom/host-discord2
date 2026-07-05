from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.database import SessionLocal, init_db
from app.models.bot import Bot
from app.routers import bots, console, env_vars, files, logs, monitoring
from app.services.process_manager import process_manager

app = FastAPI(title="Bot Panel API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(bots.router)
app.include_router(files.router)
app.include_router(env_vars.router)
app.include_router(monitoring.router)
app.include_router(logs.router)
app.include_router(console.router)


@app.get("/health")
def health():
    # Rota pública (sem chave) só para confirmar que o backend está de pé.
    # Não expõe nenhuma informação sensível.
    return {"status": "ok"}


@app.on_event("startup")
async def startup_event() -> None:
    init_db()

    # Inicialização automática dos bots marcados com autostart_on_boot
    db = SessionLocal()
    try:
        bots_to_start = db.query(Bot).filter(Bot.autostart_on_boot == True).all()  # noqa: E712
        for bot in bots_to_start:
            folder = settings.bots_dir_path / bot.folder_name
            bp = process_manager.get_or_create(bot.id, folder, bot.start_command)
            try:
                await bp.start()
                bot.status = "running"
                bot.pid = bp.pid
            except Exception as exc:  # noqa: BLE001
                bot.status = "crashed"
                bot.last_error = str(exc)
        db.commit()
    finally:
        db.close()
