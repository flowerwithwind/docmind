"""DocMind FastAPI 应用入口。"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import (
    chat,
    compares,
    data,
    demo,
    documents,
    extractions,
    health,
    media,
    samples,
    schemas,
    settings,
    table_qa,
    tasks,
)
from app.config import PROJECT_ROOT, ensure_dirs
from app.seed import ensure_seed_schemas
from app.services.table_store import table_store
from app.storage import db
from app.utils.limits import RateLimitMiddleware
from app.utils.logging import get_logger

logger = get_logger("main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    ensure_dirs()
    db.init_db()
    ensure_seed_schemas()
    table_store.ensure_demo()  # B2：无 Key 时也内置演示表可查询
    db.fail_stale_tasks()
    logger.info("DocMind 启动完成")
    yield


def _read_version() -> str:
    """读取 VERSION 文件作为应用版本（与健康检查保持一致）。"""
    try:
        return (PROJECT_ROOT / "VERSION").read_text(encoding="utf-8").strip()
    except OSError:
        return "0.0.0"


app = FastAPI(
    title="DocMind API",
    description="多模态文档智能助手后端",
    version=_read_version(),
    lifespan=lifespan,
)

app.add_middleware(RateLimitMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(schemas.router)
app.include_router(tasks.router)
app.include_router(documents.router)
app.include_router(media.router)
app.include_router(settings.router)
app.include_router(demo.router)
app.include_router(chat.sessions_router)
app.include_router(chat.chat_router)
app.include_router(extractions.documents_router)
app.include_router(extractions.router)
app.include_router(samples.router)
app.include_router(compares.router)
app.include_router(data.router)
app.include_router(table_qa.router)


