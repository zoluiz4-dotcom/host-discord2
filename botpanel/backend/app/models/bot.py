import datetime
import uuid

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class Bot(Base):
    __tablename__ = "bots"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(String, default="")

    # Como o bot é iniciado, ex: "python main.py" ou "node index.js"
    start_command: Mapped[str] = mapped_column(String, nullable=False)

    # Pasta do bot dentro de BOTS_DIR (isolada por bot)
    folder_name: Mapped[str] = mapped_column(String, nullable=False, unique=True)

    runtime: Mapped[str] = mapped_column(String, default="python")  # python | node | docker
    docker_image: Mapped[str] = mapped_column(String, default="python:3.12-slim")

    auto_restart: Mapped[bool] = mapped_column(Boolean, default=True)
    autostart_on_boot: Mapped[bool] = mapped_column(Boolean, default=True)

    status: Mapped[str] = mapped_column(String, default="stopped")  # running | stopped | crashed
    pid: Mapped[int | None] = mapped_column(Integer, nullable=True)
    container_id: Mapped[str | None] = mapped_column(String, nullable=True)

    last_started_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)
    last_error: Mapped[str] = mapped_column(Text, default="")

    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=datetime.datetime.utcnow
    )

    restarts: Mapped[list["RestartLog"]] = relationship(
        back_populates="bot", cascade="all, delete-orphan"
    )


class RestartLog(Base):
    __tablename__ = "restart_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    bot_id: Mapped[str] = mapped_column(ForeignKey("bots.id"))
    reason: Mapped[str] = mapped_column(String, default="manual")  # manual | crash | boot
    timestamp: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=datetime.datetime.utcnow
    )

    bot: Mapped["Bot"] = relationship(back_populates="restarts")
