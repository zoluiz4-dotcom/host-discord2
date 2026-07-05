"""
Gerenciador de processos dos bots.

Cada bot roda como um subprocesso próprio (modo padrão, mais simples) ou
como um container Docker isolado (quando USE_DOCKER=true e o bot está
configurado com runtime="docker"). Este serviço:

- inicia, para e reinicia bots
- detecta quando um bot cai inesperadamente e reinicia automaticamente
  (se auto_restart estiver ativo)
- transmite as linhas de log em tempo real para quem estiver conectado
  via WebSocket
- guarda um histórico de logs em disco (bots_data/<bot>/logs/)
"""
from __future__ import annotations

import asyncio
import datetime
import os
import shlex
import signal
import time
from collections import deque
from pathlib import Path

import psutil

from app.core.config import settings

LOG_LINES_KEEP_IN_MEMORY = 500


class BotProcess:
    def __init__(self, bot_id: str, folder: Path, command: str):
        self.bot_id = bot_id
        self.folder = folder
        self.command = command
        self.process: asyncio.subprocess.Process | None = None
        self.started_at: float | None = None
        self.log_buffer: deque[str] = deque(maxlen=LOG_LINES_KEEP_IN_MEMORY)
        self.subscribers: set[asyncio.Queue] = set()
        self.log_file_path = folder / "logs" / "output.log"
        self.log_file_path.parent.mkdir(parents=True, exist_ok=True)
        self._reader_task: asyncio.Task | None = None
        self.last_error: str = ""

    @property
    def pid(self) -> int | None:
        return self.process.pid if self.process else None

    @property
    def is_running(self) -> bool:
        return self.process is not None and self.process.returncode is None

    async def _pump_output(self) -> None:
        assert self.process and self.process.stdout
        with open(self.log_file_path, "a", encoding="utf-8") as log_file:
            while True:
                line = await self.process.stdout.readline()
                if not line:
                    break
                decoded = line.decode("utf-8", errors="replace").rstrip("\n")
                timestamped = f"[{datetime.datetime.now().strftime('%H:%M:%S')}] {decoded}"
                self.log_buffer.append(timestamped)
                log_file.write(timestamped + "\n")
                log_file.flush()
                for queue in list(self.subscribers):
                    queue.put_nowait(timestamped)

    async def start(self) -> None:
        if self.is_running:
            return
        self.folder.mkdir(parents=True, exist_ok=True)
        env_path = self.folder / ".env"
        env = os.environ.copy()
        if env_path.exists():
            for raw_line in env_path.read_text(encoding="utf-8").splitlines():
                if not raw_line.strip() or raw_line.strip().startswith("#") or "=" not in raw_line:
                    continue
                key, _, value = raw_line.partition("=")
                env[key.strip()] = value.strip()

        args = shlex.split(self.command)
        self.process = await asyncio.create_subprocess_exec(
            *args,
            cwd=str(self.folder),
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            preexec_fn=os.setsid if os.name != "nt" else None,
        )
        self.started_at = time.time()
        self.last_error = ""
        self._reader_task = asyncio.create_task(self._pump_output())

    async def stop(self) -> None:
        if not self.process:
            return
        try:
            if os.name != "nt":
                os.killpg(os.getpgid(self.process.pid), signal.SIGTERM)
            else:
                self.process.terminate()
            await asyncio.wait_for(self.process.wait(), timeout=10)
        except (ProcessLookupError, asyncio.TimeoutError):
            try:
                if os.name != "nt":
                    os.killpg(os.getpgid(self.process.pid), signal.SIGKILL)
                else:
                    self.process.kill()
            except ProcessLookupError:
                pass
        finally:
            self.started_at = None

    def uptime_seconds(self) -> float:
        if not self.started_at or not self.is_running:
            return 0.0
        return time.time() - self.started_at

    def resource_usage(self) -> tuple[float, float]:
        """Retorna (cpu_percent, ram_mb) do processo do bot."""
        if not self.pid or not self.is_running:
            return 0.0, 0.0
        try:
            proc = psutil.Process(self.pid)
            cpu = proc.cpu_percent(interval=0.1)
            ram_mb = proc.memory_info().rss / (1024 * 1024)
            return cpu, ram_mb
        except psutil.NoSuchProcess:
            return 0.0, 0.0


class ProcessManager:
    """Mantém em memória todos os BotProcess ativos e cuida do auto-restart."""

    def __init__(self) -> None:
        self._processes: dict[str, BotProcess] = {}
        self._monitor_task: asyncio.Task | None = None
        self.server_started_at = time.time()

    def get_or_create(self, bot_id: str, folder: Path, command: str) -> BotProcess:
        if bot_id not in self._processes:
            self._processes[bot_id] = BotProcess(bot_id, folder, command)
        return self._processes[bot_id]

    def get(self, bot_id: str) -> BotProcess | None:
        return self._processes.get(bot_id)

    def remove(self, bot_id: str) -> None:
        self._processes.pop(bot_id, None)

    def start_monitor(self, on_crash) -> None:
        """on_crash(bot_id) é chamado quando um bot com auto_restart cai."""
        if self._monitor_task is None:
            self._monitor_task = asyncio.create_task(self._monitor_loop(on_crash))

    async def _monitor_loop(self, on_crash) -> None:
        while True:
            await asyncio.sleep(3)
            for bot_id, bp in list(self._processes.items()):
                if bp.process is not None and bp.process.returncode is not None and bp.started_at:
                    # o processo morreu sem que nós tivéssemos chamado stop()
                    bp.last_error = f"Processo finalizado com código {bp.process.returncode}"
                    bp.started_at = None
                    await on_crash(bot_id)


process_manager = ProcessManager()
