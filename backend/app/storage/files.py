"""文件存储：安全命名、读写、删除、类型判定。"""
from __future__ import annotations

import shutil
import uuid
from pathlib import Path

from fastapi import HTTPException, UploadFile

from app.config import ALLOWED_EXTS, FILES_DIR, IMAGES_DIR, UPLOAD_MAX_BYTES


def ext_of(filename: str) -> str:
    return Path(filename).suffix.lower()


def is_allowed(filename: str) -> bool:
    return ext_of(filename) in ALLOWED_EXTS


def safe_store(upload: UploadFile) -> tuple[str, str, int]:
    """保存上传文件，返回 (存储文件名, 原始名, 大小)。"""
    original = Path(upload.filename or "unnamed").name  # 去路径，防穿越
    ext = ext_of(original)
    if ext not in ALLOWED_EXTS:
        raise HTTPException(status_code=422, detail=f"不支持的文件类型 {ext or '(无扩展名)'}")
    if upload.size and upload.size > UPLOAD_MAX_BYTES:
        raise HTTPException(status_code=413, detail="文件超过 50MB 限制")
    stored = f"{uuid.uuid4().hex}{ext}"
    target = FILES_DIR / stored
    size = 0
    with target.open("wb") as out:
        while True:
            chunk = upload.file.read(1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            if size > UPLOAD_MAX_BYTES:
                out.close()
                target.unlink(missing_ok=True)
                raise HTTPException(status_code=413, detail="文件超过 50MB 限制")
            out.write(chunk)
    return stored, original, size


def file_path(filename: str) -> Path:
    return FILES_DIR / filename


def image_path(filename: str) -> Path:
    return IMAGES_DIR / filename


def save_image_bytes(filename: str, data: bytes) -> str:
    """保存解析出的图片，返回存储文件名。"""
    target = IMAGES_DIR / filename
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    return filename


def remove_document_files(filename: str) -> None:
    (FILES_DIR / filename).unlink(missing_ok=True)


def remove_image(name: str) -> None:
    (IMAGES_DIR / name).unlink(missing_ok=True)


def copy_seed_to_store(seed_file: Path) -> str:
    """把种子样例复制到文件存储，返回存储文件名。"""
    stored = f"{uuid.uuid4().hex}{seed_file.suffix.lower()}"
    shutil.copyfile(seed_file, FILES_DIR / stored)
    return stored
