from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.security import require_api_key
from app.models.bot import Bot
from app.models.schemas import (
    FileContent,
    FileNode,
    FileOpCopyMove,
    FileOpCreate,
    FileOpRename,
    FileWrite,
)
from app.services import file_service

router = APIRouter(
    prefix="/api/bots/{bot_id}/files", tags=["files"], dependencies=[Depends(require_api_key)]
)


def _bot_folder(bot_id: str, db: Session):
    bot = db.query(Bot).filter(Bot.id == bot_id).first()
    if not bot:
        raise HTTPException(status_code=404, detail="Bot não encontrado.")
    folder = settings.bots_dir_path / bot.folder_name
    folder.mkdir(parents=True, exist_ok=True)
    return folder


@router.get("/tree", response_model=FileNode)
def get_tree(bot_id: str, db: Session = Depends(get_db)):
    folder = _bot_folder(bot_id, db)
    return file_service.build_tree(folder)


@router.get("/content", response_model=FileContent)
def get_content(bot_id: str, path: str, db: Session = Depends(get_db)):
    folder = _bot_folder(bot_id, db)
    content = file_service.read_text_file(folder, path)
    return FileContent(path=path, content=content)


@router.put("/content")
def write_content(bot_id: str, payload: FileWrite, db: Session = Depends(get_db)):
    folder = _bot_folder(bot_id, db)
    file_service.write_text_file(folder, payload.path, payload.content)
    return {"ok": True}


@router.post("/create", status_code=201)
def create_entry(bot_id: str, payload: FileOpCreate, db: Session = Depends(get_db)):
    folder = _bot_folder(bot_id, db)
    file_service.create_node(folder, payload.path, payload.is_dir)
    return {"ok": True}


@router.delete("/delete")
def delete_entry(bot_id: str, path: str, db: Session = Depends(get_db)):
    folder = _bot_folder(bot_id, db)
    file_service.delete_node(folder, path)
    return {"ok": True}


@router.post("/rename")
def rename_entry(bot_id: str, payload: FileOpRename, db: Session = Depends(get_db)):
    folder = _bot_folder(bot_id, db)
    file_service.rename_node(folder, payload.old_path, payload.new_path)
    return {"ok": True}


@router.post("/copy")
def copy_entry(bot_id: str, payload: FileOpCopyMove, db: Session = Depends(get_db)):
    folder = _bot_folder(bot_id, db)
    file_service.copy_node(folder, payload.source_path, payload.dest_path)
    return {"ok": True}


@router.post("/move")
def move_entry(bot_id: str, payload: FileOpCopyMove, db: Session = Depends(get_db)):
    folder = _bot_folder(bot_id, db)
    file_service.move_node(folder, payload.source_path, payload.dest_path)
    return {"ok": True}


@router.get("/download")
def download_file(bot_id: str, path: str, db: Session = Depends(get_db)):
    folder = _bot_folder(bot_id, db)
    target = file_service.resolve_safe_path(folder, path)
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="Arquivo não encontrado.")
    return FileResponse(target, filename=target.name)


@router.post("/upload", status_code=201)
async def upload_file(
    bot_id: str, path: str, file: UploadFile, db: Session = Depends(get_db)
):
    folder = _bot_folder(bot_id, db)
    dest = file_service.resolve_safe_path(folder, path)
    dest.parent.mkdir(parents=True, exist_ok=True)

    size = 0
    with open(dest, "wb") as out:
        while chunk := await file.read(1024 * 1024):
            size += len(chunk)
            if size > file_service.MAX_UPLOAD_SIZE_BYTES:
                out.close()
                dest.unlink(missing_ok=True)
                raise HTTPException(status_code=413, detail="Arquivo excede o limite de 200MB.")
            out.write(chunk)
    return {"ok": True, "path": path}


@router.post("/extract-zip")
def extract_zip(bot_id: str, zip_path: str, dest_path: str = "", db: Session = Depends(get_db)):
    folder = _bot_folder(bot_id, db)
    file_service.extract_zip(folder, zip_path, dest_path)
    return {"ok": True}


@router.post("/compress-zip")
def compress_zip(
    bot_id: str, paths: list[str], zip_name: str, db: Session = Depends(get_db)
):
    folder = _bot_folder(bot_id, db)
    file_service.compress_to_zip(folder, paths, zip_name)
    return {"ok": True, "zip_name": zip_name}
