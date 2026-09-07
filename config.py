"""Application configuration and safe secret loading."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse


APP_NAME = "スロット期待値"
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


_SUPABASE_SECRET_ALIASES = {
    "SUPABASE_URL": ("url", "SUPABASE_URL"),
    "SUPABASE_ANON_KEY": ("anon_key", "SUPABASE_ANON_KEY"),
    "SUPABASE_SERVICE_ROLE_KEY": ("service_role_key", "SUPABASE_SERVICE_ROLE_KEY"),
    "APP_ADMIN_EMAILS": ("APP_ADMIN_EMAILS", "admin_emails"),
}


def _get_streamlit_secret(name: str) -> Any | None:
    try:
        import streamlit as st
    except Exception:
        return None

    try:
        if name in st.secrets:
            return st.secrets[name]

        supabase = st.secrets.get("supabase", {})
        for key in _SUPABASE_SECRET_ALIASES.get(name, ()):
            if key in supabase:
                return supabase[key]
    except Exception:
        return None

    return None


def get_secret(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name)
    if value not in (None, ""):
        return value.strip()

    value = _get_streamlit_secret(name)
    if value not in (None, ""):
        return str(value).strip()

    return default


def get_required_secret(name: str) -> str:
    value = get_secret(name)
    if not value:
        raise RuntimeError(f"{name} が設定されていません。Streamlit Secrets または環境変数を確認してください。")
    return value


def _looks_like_placeholder(value: str) -> bool:
    lowered = value.lower()
    return any(
        marker in lowered
        for marker in (
            "your-project-ref",
            "your-supabase",
            "your-anon-key",
            "your-service-role-key",
            "example.supabase.co",
        )
    )


def _normalize_supabase_url(url: str) -> str:
    if _looks_like_placeholder(url):
        raise RuntimeError("SUPABASE_URL がサンプル値のままです。実際の Supabase Project URL を設定してください。")
    if any(char.isspace() for char in url):
        raise RuntimeError("SUPABASE_URL に空白文字が含まれています。前後や途中の空白を削除してください。")

    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise RuntimeError("SUPABASE_URL の形式が不正です。例: https://your-project-ref.supabase.co")
    return url.rstrip("/")


def _normalize_supabase_key(name: str, value: str | None) -> str | None:
    if value is None:
        return None
    if _looks_like_placeholder(value):
        raise RuntimeError(f"{name} がサンプル値のままです。Supabase の実際の API key を設定してください。")
    if any(char.isspace() for char in value):
        raise RuntimeError(f"{name} に空白文字が含まれています。コピー時に混入した改行や空白を削除してください。")
    return value


def get_supabase_settings(require_service_role: bool = False) -> SupabaseSettings:
    settings = SupabaseSettings(
        url=_normalize_supabase_url(get_required_secret("SUPABASE_URL")),
        anon_key=_normalize_supabase_key("SUPABASE_ANON_KEY", get_required_secret("SUPABASE_ANON_KEY")) or "",
        service_role_key=_normalize_supabase_key("SUPABASE_SERVICE_ROLE_KEY", get_secret("SUPABASE_SERVICE_ROLE_KEY")),
    )
    if require_service_role and not settings.service_role_key:
        raise RuntimeError("SUPABASE_SERVICE_ROLE_KEY が設定されていないため、この管理操作は実行できません。")
    return settings


def get_admin_emails() -> set[str]:
    raw = get_secret("APP_ADMIN_EMAILS", "") or ""
    return {email.strip().lower() for email in raw.split(",") if email.strip()}
