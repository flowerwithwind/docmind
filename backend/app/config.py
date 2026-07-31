"""DocMind 全局配置。

所有路径与默认值集中于此，测试通过环境变量 DOCMIND_DATA_DIR 重定向数据目录。
"""
from __future__ import annotations

import os
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = BACKEND_DIR.parent

# 数据目录（可用环境变量重定向，测试使用）
DATA_DIR = Path(os.environ.get("DOCMIND_DATA_DIR", PROJECT_ROOT / "data"))
FILES_DIR = DATA_DIR / "files"
IMAGES_DIR = DATA_DIR / "images"
EXPORTS_DIR = DATA_DIR / "exports"
DB_PATH = DATA_DIR / "docmind.db"
SEED_DIR = PROJECT_ROOT / "seed"

UPLOAD_MAX_BYTES = 50 * 1024 * 1024
ALLOWED_EXTS = {".pdf", ".docx", ".xlsx", ".png", ".jpg", ".jpeg", ".webp"}
MAX_FILES_PER_UPLOAD = 5

# 模型默认值（settings 表可覆盖；环境变量便于无 UI 配置）
DEFAULT_MODEL = os.environ.get("DOCMIND_MODEL", "deepseek-chat")
DEFAULT_BASE_URL = os.environ.get("DOCMIND_BASE_URL", "https://api.deepseek.com/v1")
DEFAULT_API_KEY = os.environ.get("DOCMIND_API_KEY", "")
DEFAULT_TEMPERATURE = 0.2
DEFAULT_MAX_TOKENS = 4096
DEFAULT_TOP_K = 6
DEFAULT_RRF_K = 60
DEFAULT_CONTEXT_LIMIT = 8000
DEFAULT_CHUNK_MAX_CHARS = 1500
DEFAULT_CHUNK_MIN_CHARS = 80
DEFAULT_EMBEDDING_MODEL = os.environ.get("DOCMIND_EMBEDDING_MODEL", "text-embedding-3-small")
DEFAULT_EMBEDDING_BASE_URL = os.environ.get("DOCMIND_EMBEDDING_BASE_URL", "")
DEFAULT_EMBEDDING_API_KEY = os.environ.get("DOCMIND_EMBEDDING_API_KEY", "")

DEMO_KINDS = ("contract", "contract_v2", "financial")

# 限流：默认 60 req/min/IP
RATE_LIMIT_PER_MINUTE = int(os.environ.get("DOCMIND_RATE_LIMIT", "60"))


def ensure_dirs() -> None:
    """确保数据目录存在（启动时调用）。"""
    for d in (DATA_DIR, FILES_DIR, IMAGES_DIR, EXPORTS_DIR):
        d.mkdir(parents=True, exist_ok=True)
