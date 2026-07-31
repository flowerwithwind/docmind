"""设置 API。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from app.models import SettingsOut
from app.services import settings as settings_svc

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("")
def get_settings() -> SettingsOut:
    return SettingsOut(
        model=settings_svc.get_model_settings(),
        retrieval=settings_svc.get_retrieval_settings(),
        capabilities=settings_svc.get_capabilities(),
    )


@router.put("")
def update_settings(body: dict[str, Any]) -> SettingsOut:
    if "model" in body:
        settings_svc.save_model_settings(body["model"])
    if "retrieval" in body:
        settings_svc.save_retrieval_settings(body["retrieval"])
    return get_settings()


@router.post("/test")
def test_connection(body: dict[str, Any]) -> dict[str, Any]:
    return settings_svc.test_connection(body.get("model") or {})
