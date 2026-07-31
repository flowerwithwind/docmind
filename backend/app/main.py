"""DocMind FastAPI 应用入口。"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import demo, health, schemas, settings, tasks
from app.config import ensure_dirs
from app.seed import ensure_seed_schemas
from app.storage import db
from app.utils.limits import RateLimitMiddleware
from app.utils.logging import get_logger

logger = get_logger("main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    ensure_dirs()
    db.init_db()
    ensure_seed_schemas()
    db.fail_stale_tasks()
    logger.info("DocMind 启动完成")
    yield


app = FastAPI(
    title="DocMind API",
    description="多模态文档智能助手后端",
    version="0.1.0",
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
app.include_router(settings.router)
app.include_router(demo.router)
