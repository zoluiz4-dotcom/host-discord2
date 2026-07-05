import datetime

from pydantic import BaseModel, Field


class BotCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    description: str = ""
    start_command: str = Field(min_length=1, max_length=200)
    runtime: str = "python"  # python | node | docker
    docker_image: str = "python:3.12-slim"
    auto_restart: bool = True
    autostart_on_boot: bool = True


class BotUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    start_command: str | None = None
    auto_restart: bool | None = None
    autostart_on_boot: bool | None = None
    docker_image: str | None = None


class BotOut(BaseModel):
    id: str
    name: str
    description: str
    start_command: str
    folder_name: str
    runtime: str
    docker_image: str
    auto_restart: bool
    autostart_on_boot: bool
    status: str
    pid: int | None
    last_started_at: datetime.datetime | None
    last_error: str
    created_at: datetime.datetime

    model_config = {"from_attributes": True}


class RestartLogOut(BaseModel):
    id: int
    reason: str
    timestamp: datetime.datetime

    model_config = {"from_attributes": True}


class FileNode(BaseModel):
    name: str
    path: str  # caminho relativo dentro da pasta do bot
    is_dir: bool
    size: int = 0
    modified_at: datetime.datetime | None = None
    children: list["FileNode"] | None = None


class FileContent(BaseModel):
    path: str
    content: str


class FileWrite(BaseModel):
    path: str
    content: str


class FileOpCreate(BaseModel):
    path: str
    is_dir: bool = False


class FileOpRename(BaseModel):
    old_path: str
    new_path: str


class FileOpCopyMove(BaseModel):
    source_path: str
    dest_path: str


class EnvVarsOut(BaseModel):
    variables: dict[str, str]


class EnvVarsIn(BaseModel):
    variables: dict[str, str]
    restart_bot: bool = True


class SystemStats(BaseModel):
    cpu_percent: float
    ram_percent: float
    ram_used_mb: float
    ram_total_mb: float
    disk_percent: float
    disk_used_gb: float
    disk_total_gb: float
    uptime_seconds: float
    bots_online: int
    bots_offline: int


class BotStats(BaseModel):
    bot_id: str
    status: str
    pid: int | None
    cpu_percent: float
    ram_mb: float
    uptime_seconds: float
    last_error: str
