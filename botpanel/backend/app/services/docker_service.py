"""
Isolamento via Docker (opcional).

Quando um bot é criado com runtime="docker", cada execução acontece dentro
de um container próprio, isolado dos demais bots e do sistema host. Isso é
mais seguro que subprocessos diretos, mas exige que o backend tenha acesso
ao socket do Docker (/var/run/docker.sock) — veja docker-compose.yml.

Este módulo só é usado quando USE_DOCKER=true nas configurações.
"""
from __future__ import annotations

from pathlib import Path

import docker
from docker.errors import NotFound

_client: docker.DockerClient | None = None


def get_client() -> docker.DockerClient:
    global _client
    if _client is None:
        _client = docker.from_env()
    return _client


def container_name(bot_id: str) -> str:
    return f"botpanel-{bot_id}"


def start_container(bot_id: str, folder: Path, image: str, command: str) -> str:
    client = get_client()
    name = container_name(bot_id)

    try:
        existing = client.containers.get(name)
        existing.remove(force=True)
    except NotFound:
        pass

    container = client.containers.run(
        image,
        command=["sh", "-c", command],
        name=name,
        working_dir="/bot",
        volumes={str(folder.resolve()): {"bind": "/bot", "mode": "rw"}},
        detach=True,
        mem_limit="512m",
        nano_cpus=1_000_000_000,  # limite de 1 CPU
        network_mode="bridge",
        restart_policy={"Name": "no"},
    )
    return container.id


def stop_container(bot_id: str) -> None:
    client = get_client()
    try:
        container = client.containers.get(container_name(bot_id))
        container.stop(timeout=10)
        container.remove(force=True)
    except NotFound:
        pass


def get_container_logs(bot_id: str, tail: int = 500) -> str:
    client = get_client()
    try:
        container = client.containers.get(container_name(bot_id))
        return container.logs(tail=tail).decode("utf-8", errors="replace")
    except NotFound:
        return ""


def is_container_running(bot_id: str) -> bool:
    client = get_client()
    try:
        container = client.containers.get(container_name(bot_id))
        return container.status == "running"
    except NotFound:
        return False
