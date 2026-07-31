"""演示信息 API（样例加载在 M5 提供）。"""
from __future__ import annotations

from fastapi import APIRouter

from app.models import DemoInfo
from app.seed import DEMO_QUESTIONS, DEMO_SAMPLES
from app.services import settings as settings_svc

router = APIRouter(prefix="/api/demo", tags=["demo"])


@router.get("")
def demo_info() -> DemoInfo:
    return DemoInfo(
        samples=[dict(s) for s in DEMO_SAMPLES],
        questions=DEMO_QUESTIONS,
        capabilities=settings_svc.get_capabilities(),
    )
