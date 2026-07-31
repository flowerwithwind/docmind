"""Pydantic 数据模型与枚举。"""
from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


def now_iso() -> str:
    # 全项目统一使用本地时间（无时区），避免 UI 展示混乱
    return datetime.now().isoformat(timespec="seconds")  # noqa: DTZ005


class DocStatus(StrEnum):
    UPLOADED = "uploaded"
    PARSING = "parsing"
    PARSED = "parsed"
    FAILED = "failed"


class ChunkKind(StrEnum):
    TEXT = "text"
    TABLE = "table"
    IMAGE = "image"


class TaskStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class TaskKind(StrEnum):
    PARSE = "parse"
    EXTRACT = "extract"
    COMPARE = "compare"
    DEMO_LOAD = "demo_load"


class ExtractionStatus(StrEnum):
    DRAFT = "draft"
    CONFIRMED = "confirmed"


class FieldType(StrEnum):
    STRING = "string"
    NUMBER = "number"
    DATE = "date"
    LIST = "list"
    OBJECT = "object"


class FieldStatus(StrEnum):
    EXTRACTED = "extracted"
    UNSURE = "unsure"
    MISSING = "missing"
    INVALID = "invalid"


class ExtractionSource(StrEnum):
    LLM = "llm"
    RULE = "rule"


class Citation(BaseModel):
    chunk_id: int
    page: int | None = None
    section: str = ""
    snippet: str = ""


class FieldDef(BaseModel):
    key: str = Field(min_length=1, max_length=64, pattern=r"^[a-z][a-z0-9_]*$")
    label: str = Field(min_length=1, max_length=64)
    type: FieldType = FieldType.STRING
    required: bool = False
    description: str = ""
    example: str = ""
    prompt_hint: str = ""
    enum: list[str] = []


class SchemaIn(BaseModel):
    key: str = Field(min_length=1, max_length=64, pattern=r"^[a-z][a-z0-9_]*$")
    name: str = Field(min_length=1, max_length=64)
    description: str = ""
    fields: list[FieldDef] = Field(min_length=1)


class SchemaOut(SchemaIn):
    id: int
    is_builtin: bool = False
    created_at: str


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    original_name: str
    ext: str
    size_bytes: int
    status: str
    parse_error: str | None = None
    page_count: int | None = None
    char_count: int | None = None
    chunk_count: int | None = None
    created_at: str
    updated_at: str


class ChunkOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    doc_id: int
    seq: int
    kind: str
    section_path: str | None = None
    title: str | None = None
    content: str
    page: int | None = None
    char_count: int
    token_estimate: int
    image_path: str | None = None


class TreeNode(BaseModel):
    title: str
    level: int
    page: int | None = None
    children: list[TreeNode] = []
    chunk_ids: list[int] = []


class PageBlockOut(BaseModel):
    kind: str
    text: str = ""
    table: str = ""
    image_path: str | None = None
    page: int | None = None
    heading_level: int | None = None


class PageOut(BaseModel):
    page: int
    blocks: list[PageBlockOut] = []


class TaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    kind: str
    status: str
    progress: int
    message: str = ""
    result_json: str | None = None
    error: str | None = None
    created_at: str
    finished_at: str | None = None


class SessionOut(BaseModel):
    id: int
    title: str
    doc_ids: list[int]
    created_at: str


class MessageOut(BaseModel):
    id: int
    session_id: int
    role: str
    content: str
    citations: list[Citation] = []
    source: str = "llm"
    created_at: str


class ExtractionOut(BaseModel):
    id: int
    doc_id: int
    schema_id: int
    status: str
    data: dict[str, Any] = {}
    confidence: dict[str, float] = {}
    field_status: dict[str, str] = {}
    citations: dict[str, list[Citation]] = {}
    source: str = "llm"
    error: str | None = None
    confirmed_at: str | None = None
    created_at: str
    updated_at: str


class SampleOut(BaseModel):
    id: int
    extraction_id: int | None
    doc_id: int
    schema_id: int
    field_key: str
    model_value: str | None = None
    human_value: str
    citation: str = ""
    created_at: str


class FieldDiff(BaseModel):
    key: str
    label: str
    value_a: Any = None
    value_b: Any = None
    status: str  # same / changed / only_a / only_b / both_missing
    delta_pct: float | None = None


class SectionDiff(BaseModel):
    title: str
    status: str  # same / changed / added / removed
    similarity: float


class CompareResult(BaseModel):
    id: int
    doc_a_id: int
    doc_b_id: int
    schema_id: int
    field_diff: list[FieldDiff] = []
    section_diff: list[SectionDiff] = []
    summary: str = ""
    source: str = "rule"
    created_at: str


class ChatRequest(BaseModel):
    session_id: int | None = None
    question: str = Field(min_length=1, max_length=4000)
    doc_ids: list[int] = Field(min_length=1)
    stream: bool = True


class DemoInfo(BaseModel):
    samples: list[dict[str, str]]
    questions: list[str]
    capabilities: dict[str, bool]


class SettingsOut(BaseModel):
    model: dict[str, Any]
    retrieval: dict[str, Any]
    capabilities: dict[str, bool]
