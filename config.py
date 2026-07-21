"""Application configuration and safe secret loading."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any


APP_NAME = "マルハン綾瀬上土棚店・設定狙い分析"
STORE_NAME = "マルハン綾瀬上土棚店"
ANA_SLO_DOMAIN = "ana-slo.com"
MIN_IMPORT_INTERVAL_SECONDS = 60

ROLE_ADMIN = "admin"
ROLE_VIEWER = "viewer"
VALID_ROLES = (ROLE_ADMIN, ROLE_VIEWER)

DEFAULT_SPECIAL_DAY_SUFFIXES = {"1", "3", "5", "6", "7", "8"}
ANNIVERSARY_MONTH_DAY = (12, 26)

WEEKDAY_JP = {
    0: "月",
    1: "火",
    2: "水",
    3: "木",
    4: "金",
    5: "土",
    6: "日",
}


@dataclass(frozen=True)
class SupabaseSettings:
    url: str
    anon_key: str
    service_role_key: str | None = None


def _get_streamlit_secret(name: str) -> Any | None:
    try:
        import streamlit as st
    except Exception:
        return None

    try:
        if name in st.secrets:
            return st.secrets[name]

        supabase = st.secrets.get("supabase", {})
        mapped = {
            "SUPABASE_URL": "url",
            "SUPABASE_ANON_KEY": "anon_key",
            "SUPABASE_SERVICE_ROLE_KEY": "service_role_key",
        }
        if name in mapped and mapped[name] in supabase:
            return supabase[mapped[name]]
    except Exception:
        return None

    return None


def get_secret(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name)
    if value not in (None, ""):
        return value

    value = _get_streamlit_secret(name)
    if value not in (None, ""):
        return str(value)

    return default


def get_required_secret(name: str) -> str:
    value = get_secret(name)
    if not value:
        raise RuntimeError(f"{name} が設定されていません。Streamlit Secrets または環境変数を確認してください。")
    return value


def get_supabase_settings(require_service_role: bool = False) -> SupabaseSettings:
    settings = SupabaseSettings(
        url=get_required_secret("SUPABASE_URL"),
        anon_key=get_required_secret("SUPABASE_ANON_KEY"),
        service_role_key=get_secret("SUPABASE_SERVICE_ROLE_KEY"),
    )
    if require_service_role and not settings.service_role_key:
        raise RuntimeError("SUPABASE_SERVICE_ROLE_KEY が設定されていないため、この管理操作は実行できません。")
    return settings


def get_admin_emails() -> set[str]:
    raw = get_secret("APP_ADMIN_EMAILS", "") or ""
    return {email.strip().lower() for email in raw.split(",") if email.strip()}

