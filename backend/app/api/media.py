"""媒体 API：安全地提供解析产出的图片。"""
from __future__ import annotations

import re

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.config import IMAGES_DIR

router = APIRouter(prefix="/api/media", tags=["media"])

_SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.\-]{0,127}$")


@router.get("/images/{name}")
def get_image(name: str) -> FileResponse:
    if not _SAFE_NAME.fullmatch(name):
        raise HTTPException(status_code=400, detail="非法的图片文件名")
    path = (IMAGES_DIR / name).resolve()
    if not str(path).startswith(str(IMAGES_DIR.resolve())) or not path.is_file():
        raise HTTPException(status_code=404, detail="图片不存在")
    return FileResponse(path, media_type="image/png")
