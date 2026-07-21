"""Database access layer for Supabase.

The functions here keep Streamlit pages small and make it easier to replace
Supabase calls in tests or future batch jobs.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Iterable

import pandas as pd

from config import ROLE_ADMIN, ROLE_VIEWER, VALID_ROLES, get_supabase_settings


try:
    from supabase import Client, create_client
except Exception:  # pragma: no cover - exercised only when dependency missing
    Client = Any  # type: ignore
    create_client = None  # type: ignore


MACHINE_RECORD_COLUMNS = [
    "id",
    "store_name",
    "date",
    "machine_no",
    "machine_name",
    "games",
    "diff_coins",
    "bb",
    "rb",
    "at_hits",
    "first_hits",
    "special_day",
    "source_url",
    "fetched_at",
    "created_at",
    "updated_at",
]


def get_supabase_client(access_token: str | None = None, use_service_role: bool = False) -> Client:
    if create_client is None:
        raise RuntimeError("supabase パッケージがインストールされていません。`pip install -r requirements.txt` を実行してください。")
    settings = get_supabase_settings(require_service_role=use_service_role)
    key = settings.service_role_key if use_service_role else settings.anon_key
    client = create_client(settings.url, key)
    if access_token:
        client.postgrest.auth(access_token)
    return client


def _data(response: Any) -> list[dict[str, Any]]:
    return list(getattr(response, "data", None) or [])


def fetch_all(table_name: str, access_token: str | None = None, use_service_role: bool = False, page_size: int = 1000) -> list[dict[str, Any]]:
    client = get_supabase_client(access_token=access_token, use_service_role=use_service_role)
    rows: list[dict[str, Any]] = []
    start = 0
    while True:
        response = client.table(table_name).select("*").range(start, start + page_size - 1).execute()
        chunk = _data(response)
        rows.extend(chunk)
        if len(chunk) < page_size:
            break
        start += page_size
    return rows


def fetch_machine_records(
    access_token: str | None,
    start_date: date | str | None = None,
    end_date: date | str | None = None,
    store_name: str | None = None,
) -> list[dict[str, Any]]:
    client = get_supabase_client(access_token=access_token)
    query = client.table("machine_records").select("*").order("date", desc=False).order("machine_no", desc=False)
    if start_date:
        query = query.gte("date", str(start_date))
    if end_date:
        query = query.lte("date", str(end_date))
    if store_name:
        query = query.eq("store_name", store_name)
    rows: list[dict[str, Any]] = []
    start = 0
    page_size = 1000
    while True:
        response = query.range(start, start + page_size - 1).execute()
        chunk = _data(response)
        rows.extend(chunk)
        if len(chunk) < page_size:
            break
        start += page_size
    return rows


def records_to_dataframe(rows: Iterable[dict[str, Any]]) -> pd.DataFrame:
    df = pd.DataFrame(list(rows))
    if df.empty:
        return pd.DataFrame(columns=MACHINE_RECORD_COLUMNS)

    for col in MACHINE_RECORD_COLUMNS:
        if col not in df.columns:
            df[col] = None

    df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.date
    for col in ["machine_no", "games", "diff_coins", "bb", "rb", "at_hits", "first_hits"]:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)
    df["special_day"] = df["special_day"].fillna(False).astype(bool)
    return df[MACHINE_RECORD_COLUMNS]


def _serialize(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return value


def normalize_record_payload(record: dict[str, Any]) -> dict[str, Any]:
    payload = {key: _serialize(value) for key, value in dict(record).items() if key in MACHINE_RECORD_COLUMNS}
    payload.pop("id", None)
    payload.pop("created_at", None)
    for col in ["machine_no", "games", "diff_coins", "bb", "rb", "at_hits", "first_hits"]:
        payload[col] = int(payload.get(col) or 0)
    payload["special_day"] = bool(payload.get("special_day", False))
    return payload


def _key(record: dict[str, Any]) -> tuple[str, str, int]:
    return (str(record["store_name"]), str(record["date"]), int(record["machine_no"]))


def compute_upsert_summary(existing_records: Iterable[dict[str, Any]], incoming_records: Iterable[dict[str, Any]]) -> dict[str, int]:
    existing_keys = {_key(normalize_record_payload(row)) for row in existing_records}
    incoming_payloads = [normalize_record_payload(row) for row in incoming_records]
    incoming_keys = {_key(row) for row in incoming_payloads}
    updated = len(incoming_keys & existing_keys)
    added = len(incoming_keys - existing_keys)
    return {"records_added": added, "records_updated": updated, "records_total": len(incoming_keys)}


def upsert_machine_records(records: list[dict[str, Any]], access_token: str | None) -> dict[str, int]:
    if not records:
        return {"records_added": 0, "records_updated": 0, "records_total": 0}

    payloads = [normalize_record_payload(row) for row in records]
    client = get_supabase_client(access_token=access_token)
    existing: list[dict[str, Any]] = []
    for store_name, target_date in sorted({(row["store_name"], row["date"]) for row in payloads}):
        existing.extend(
            _data(
                client.table("machine_records")
                .select("store_name,date,machine_no")
                .eq("store_name", store_name)
                .eq("date", target_date)
                .execute()
            )
        )
    summary = compute_upsert_summary(existing, payloads)
    client.table("machine_records").upsert(payloads, on_conflict="store_name,date,machine_no").execute()
    return summary


def delete_records_by_date(target_date: date | str, access_token: str | None, store_name: str) -> int:
    client = get_supabase_client(access_token=access_token)
    existing = _data(
        client.table("machine_records")
        .select("id")
        .eq("store_name", store_name)
        .eq("date", str(target_date))
        .execute()
    )
    client.table("machine_records").delete().eq("store_name", store_name).eq("date", str(target_date)).execute()
    return len(existing)


def delete_records_by_machine(machine_no: int, access_token: str | None, store_name: str) -> int:
    client = get_supabase_client(access_token=access_token)
    existing = _data(
        client.table("machine_records")
        .select("id")
        .eq("store_name", store_name)
        .eq("machine_no", int(machine_no))
        .execute()
    )
    client.table("machine_records").delete().eq("store_name", store_name).eq("machine_no", int(machine_no)).execute()
    return len(existing)


def insert_import_log(
    *,
    user_id: str | None,
    source_url: str,
    target_date: str | None,
    status: str,
    records_found: int = 0,
    records_added: int = 0,
    error_message: str | None = None,
    access_token: str | None = None,
) -> None:
    client = get_supabase_client(access_token=access_token)
    client.table("import_logs").insert(
        {
            "user_id": user_id,
            "source_url": source_url,
            "target_date": target_date,
            "status": status,
            "records_found": records_found,
            "records_added": records_added,
            "error_message": error_message,
        }
    ).execute()


def fetch_import_logs(access_token: str | None, limit: int = 200, status: str | None = None) -> list[dict[str, Any]]:
    client = get_supabase_client(access_token=access_token)
    query = client.table("import_logs").select("*").order("created_at", desc=True).limit(limit)
    if status:
        query = query.eq("status", status)
    return _data(query.execute())


def fetch_recent_import_log(source_url: str, access_token: str | None) -> dict[str, Any] | None:
    client = get_supabase_client(access_token=access_token)
    rows = _data(
        client.table("import_logs")
        .select("*")
        .eq("source_url", source_url)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    return rows[0] if rows else None


def fetch_store_calendar(access_token: str | None, store_name: str) -> list[dict[str, Any]]:
    client = get_supabase_client(access_token=access_token)
    return _data(client.table("store_calendar").select("*").eq("store_name", store_name).order("date").execute())


def upsert_store_calendar(row: dict[str, Any], access_token: str | None) -> None:
    client = get_supabase_client(access_token=access_token)
    payload = {key: _serialize(value) for key, value in row.items()}
    client.table("store_calendar").upsert(payload, on_conflict="store_name,date").execute()


def get_profile(user_id: str, access_token: str | None) -> dict[str, Any] | None:
    client = get_supabase_client(access_token=access_token)
    rows = _data(client.table("profiles").select("*").eq("id", user_id).limit(1).execute())
    return rows[0] if rows else None


def ensure_profile(
    *,
    user_id: str,
    email: str,
    display_name: str,
    requested_role: str,
    access_token: str | None,
) -> dict[str, Any]:
    existing = get_profile(user_id, access_token)
    if existing:
        if requested_role == ROLE_ADMIN and existing.get("role") != ROLE_ADMIN:
            try:
                update_user_role(user_id, ROLE_ADMIN, use_service_role=True)
                existing["role"] = ROLE_ADMIN
            except Exception:
                pass
        return existing

    role = requested_role if requested_role in VALID_ROLES else ROLE_VIEWER
    payload = {
        "id": user_id,
        "email": email,
        "display_name": display_name or email,
        "role": role,
    }
    service_error: Exception | None = None
    if role == ROLE_ADMIN:
        try:
            client = get_supabase_client(use_service_role=True)
            client.table("profiles").upsert(payload, on_conflict="id").execute()
            return get_profile(user_id, access_token) or payload
        except Exception as exc:
            service_error = exc

    payload["role"] = ROLE_VIEWER
    try:
        client = get_supabase_client(access_token=access_token)
        client.table("profiles").upsert(payload, on_conflict="id").execute()
    except Exception as exc:
        hint = (
            "プロフィール作成に失敗しました。Supabase SQL Editorで sql/001_schema.sql を実行し、"
            "Streamlit Secretsの SUPABASE_URL / SUPABASE_ANON_KEY / SUPABASE_SERVICE_ROLE_KEY を確認してください。"
        )
        if service_error:
            hint += f" service_role_keyでの作成も失敗しています: {service_error}"
        raise RuntimeError(hint) from exc
    return get_profile(user_id, access_token) or payload


def list_profiles(access_token: str | None = None) -> list[dict[str, Any]]:
    """List users for the admin screen.

    Prefer the SQL RPC, which checks admin status. Fall back to service role when
    configured; the Streamlit server never sends the service key to the browser.
    """

    client = get_supabase_client(access_token=access_token)
    try:
        return _data(client.rpc("list_profiles_for_admin").execute())
    except Exception:
        service_client = get_supabase_client(use_service_role=True)
        return _data(service_client.table("profiles").select("*").order("created_at", desc=True).execute())


def update_user_role(user_id: str, role: str, access_token: str | None = None, use_service_role: bool = False) -> None:
    if role not in VALID_ROLES:
        raise ValueError("不正な権限です。")
    if use_service_role:
        client = get_supabase_client(use_service_role=True)
        client.table("profiles").update({"role": role}).eq("id", user_id).execute()
        return
    client = get_supabase_client(access_token=access_token)
    try:
        client.rpc("set_user_role", {"target_user_id": user_id, "new_role": role}).execute()
    except Exception:
        client.table("profiles").update({"role": role}).eq("id", user_id).execute()
