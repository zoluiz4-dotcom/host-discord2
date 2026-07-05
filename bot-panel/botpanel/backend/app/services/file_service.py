"""
Serviço de arquivos.

Toda operação de arquivo é restrita à pasta do bot (BOTS_DIR/<folder_name>).
`resolve_safe_path` garante que nenhum caminho (nem via "..", nem via link
simbólico, nem via caminho absoluto) escape dessa pasta — isso é o que
impede que alguém use o editor de código para ler ou escrever arquivos
fora do bot, como /etc/passwd ou os outros bots.
"""
from __future__ import annotations

import datetime
import shutil
import zipfile
from pathlib import Path

from fastapi import HTTPException, status

TEXT_EXTENSIONS = {
    ".py", ".js", ".ts", ".jsx", ".tsx", ".json", ".html", ".css", ".env",
    ".txt", ".md", ".yml", ".yaml", ".toml", ".ini", ".xml", ".sql", ".log",
    ".cfg", ".conf", ".sh", ".gitignore", ".dockerignore",
}

MAX_UPLOAD_SIZE_BYTES = 200 * 1024 * 1024  # 200 MB


def resolve_safe_path(base_dir: Path, relative_path: str) -> Path:
    """Resolve um caminho relativo garantindo que ele fica dentro de base_dir."""
    base_resolved = base_dir.resolve()
    candidate = (base_resolved / relative_path.lstrip("/\\")).resolve()
    if base_resolved != candidate and base_resolved not in candidate.parents:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Caminho inválido: fora da pasta do bot.",
        )
    return candidate


def is_text_file(path: Path) -> bool:
    return path.suffix.lower() in TEXT_EXTENSIONS or path.name.startswith(".env")


def build_tree(base_dir: Path, current: Path | None = None) -> dict:
    current = current or base_dir
    node = {
        "name": current.name if current != base_dir else base_dir.name,
        "path": str(current.relative_to(base_dir)) if current != base_dir else "",
        "is_dir": current.is_dir(),
        "size": 0,
        "modified_at": None,
        "children": None,
    }
    try:
        stat = current.stat()
        node["modified_at"] = datetime.datetime.fromtimestamp(stat.st_mtime)
        node["size"] = stat.st_size if current.is_file() else 0
    except FileNotFoundError:
        pass

    if current.is_dir():
        children = []
        for child in sorted(current.iterdir(), key=lambda p: (p.is_file(), p.name.lower())):
            if child.name in {"__pycache__", "node_modules", ".git"}:
                continue
            children.append(build_tree(base_dir, child))
        node["children"] = children
    return node


def read_text_file(base_dir: Path, relative_path: str) -> str:
    path = resolve_safe_path(base_dir, relative_path)
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="Arquivo não encontrado.")
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Este arquivo não é um arquivo de texto legível.",
        )


def write_text_file(base_dir: Path, relative_path: str, content: str) -> None:
    path = resolve_safe_path(base_dir, relative_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def create_node(base_dir: Path, relative_path: str, is_dir: bool) -> None:
    path = resolve_safe_path(base_dir, relative_path)
    if path.exists():
        raise HTTPException(status_code=409, detail="Já existe um arquivo ou pasta com esse nome.")
    if is_dir:
        path.mkdir(parents=True)
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()


def delete_node(base_dir: Path, relative_path: str) -> None:
    path = resolve_safe_path(base_dir, relative_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Arquivo ou pasta não encontrado.")
    if path.is_dir():
        shutil.rmtree(path)
    else:
        path.unlink()


def rename_node(base_dir: Path, old_relative: str, new_relative: str) -> None:
    old_path = resolve_safe_path(base_dir, old_relative)
    new_path = resolve_safe_path(base_dir, new_relative)
    if not old_path.exists():
        raise HTTPException(status_code=404, detail="Arquivo ou pasta não encontrado.")
    if new_path.exists():
        raise HTTPException(status_code=409, detail="Já existe um item com esse nome.")
    new_path.parent.mkdir(parents=True, exist_ok=True)
    old_path.rename(new_path)


def copy_node(base_dir: Path, source_relative: str, dest_relative: str) -> None:
    source = resolve_safe_path(base_dir, source_relative)
    dest = resolve_safe_path(base_dir, dest_relative)
    if not source.exists():
        raise HTTPException(status_code=404, detail="Origem não encontrada.")
    dest.parent.mkdir(parents=True, exist_ok=True)
    if source.is_dir():
        shutil.copytree(source, dest)
    else:
        shutil.copy2(source, dest)


def move_node(base_dir: Path, source_relative: str, dest_relative: str) -> None:
    source = resolve_safe_path(base_dir, source_relative)
    dest = resolve_safe_path(base_dir, dest_relative)
    if not source.exists():
        raise HTTPException(status_code=404, detail="Origem não encontrada.")
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(source), str(dest))


def compress_to_zip(base_dir: Path, relative_paths: list[str], zip_name: str) -> Path:
    zip_path = resolve_safe_path(base_dir, zip_name)
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for rel in relative_paths:
            target = resolve_safe_path(base_dir, rel)
            if target.is_dir():
                for file_path in target.rglob("*"):
                    if file_path.is_file():
                        zf.write(file_path, file_path.relative_to(base_dir))
            elif target.is_file():
                zf.write(target, target.relative_to(base_dir))
    return zip_path


def extract_zip(base_dir: Path, zip_relative_path: str, dest_relative_path: str = "") -> None:
    zip_path = resolve_safe_path(base_dir, zip_relative_path)
    dest_path = resolve_safe_path(base_dir, dest_relative_path)
    dest_path.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "r") as zf:
        for member in zf.namelist():
            # impede path traversal dentro do próprio zip (zip slip)
            member_path = (dest_path / member).resolve()
            if dest_path.resolve() not in member_path.parents and member_path != dest_path.resolve():
                continue
        zf.extractall(dest_path)
