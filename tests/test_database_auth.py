from __future__ import annotations

import base64
import json
import socket
from types import SimpleNamespace

import auth
import config
import database
import pytest


def test_compute_upsert_summary_counts_added_and_updated():
    existing = [
        {"store_name": "マルハン綾瀬上土棚店", "date": "2026-07-07", "machine_no": 601},
        {"store_name": "マルハン綾瀬上土棚店", "date": "2026-07-07", "machine_no": 602},
    ]
    incoming = [
        {"store_name": "マルハン綾瀬上土棚店", "date": "2026-07-07", "machine_no": 601, "machine_name": "A", "games": 1, "diff_coins": 1},
        {"store_name": "マルハン綾瀬上土棚店", "date": "2026-07-07", "machine_no": 603, "machine_name": "B", "games": 1, "diff_coins": 1},
    ]
    summary = database.compute_upsert_summary(existing, incoming)
    assert summary == {"records_added": 1, "records_updated": 1, "records_total": 2}


def test_dedupe_payloads_keeps_latest_duplicate_record():
    incoming = [
        {"store_name": "マルハン綾瀬上土棚店", "date": "2026-07-07", "machine_no": 601, "machine_name": "A", "games": 1000, "diff_coins": 100},
        {"store_name": "マルハン綾瀬上土棚店", "date": "2026-07-07", "machine_no": 601, "machine_name": "A", "games": 2000, "diff_coins": 500},
        {"store_name": "マルハン綾瀬上土棚店", "date": "2026-07-07", "machine_no": 602, "machine_name": "B", "games": 3000, "diff_coins": -100},
    ]
    payloads = database.dedupe_record_payloads(incoming)
    assert len(payloads) == 2
    record_601 = next(row for row in payloads if row["machine_no"] == 601)
    assert record_601["games"] == 2000
    assert record_601["diff_coins"] == 500

    summary = database.compute_upsert_summary([], incoming)
    assert summary == {"records_added": 2, "records_updated": 0, "records_total": 2}


def test_permission_checks():
    assert auth.can("admin", "import_data")
    assert auth.can("admin", "manage_users")
    assert auth.can("viewer", "view_analysis")
    assert not auth.can("viewer", "delete_data")
    assert not auth.can(None, "view_analysis")


def test_persistent_cookie_encrypts_and_expires(monkeypatch):
    monkeypatch.setenv("SESSION_COOKIE_SECRET", "test-only-secret-with-enough-entropy")
    encoded = auth._encode_refresh_token("refresh-token-value")

    assert "refresh-token-value" not in encoded
    assert auth._decode_refresh_token(encoded) == "refresh-token-value"


def test_access_token_expiry_detection(monkeypatch):
    def token(exp):
        payload = base64.urlsafe_b64encode(json.dumps({"exp": exp}).encode()).decode().rstrip("=")
        return f"header.{payload}.signature"

    monkeypatch.setattr(auth.time, "time", lambda: 1_000)
    assert auth._access_token_expires_soon(token(1_030))
    assert not auth._access_token_expires_soon(token(2_000))
    assert not auth._access_token_expires_soon("not-a-jwt")


def test_current_profile_refreshes_expired_session(monkeypatch):
    payload = base64.urlsafe_b64encode(json.dumps({"exp": 1}).encode()).decode().rstrip("=")
    auth.st.session_state.clear()
    auth.st.session_state.update(
        access_token=f"header.{payload}.signature",
        refresh_token="refresh-token",
        user={"id": "user-id", "email": "user@example.com"},
        profile={"id": "user-id", "role": "admin"},
    )
    monkeypatch.setattr(auth, "_refresh_session", lambda token: {"role": "admin", "token": token})

    profile = auth.current_profile()

    assert profile == {"role": "admin", "token": "refresh-token"}


def test_restore_session_rotates_cookie(monkeypatch):
    monkeypatch.setenv("SESSION_COOKIE_SECRET", "test-only-secret-with-enough-entropy")
    cookie = auth._encode_refresh_token("old-refresh-token")

    class FakeCookieManager:
        def __init__(self):
            self.values = {auth.SESSION_COOKIE_NAME: cookie}

        def get(self, name):
            return self.values.get(name)

        def set(self, name, value, **_kwargs):
            self.values[name] = value

        def delete(self, name, **_kwargs):
            self.values.pop(name, None)

    manager = FakeCookieManager()
    response = SimpleNamespace(
        session=SimpleNamespace(access_token="new-access-token", refresh_token="new-refresh-token"),
        user=SimpleNamespace(id="user-id", email="user@example.com"),
    )

    class FakeAuth:
        def refresh_session(self, token):
            assert token == "old-refresh-token"
            return response

    monkeypatch.setattr(auth, "_get_cookie_manager", lambda: manager)
    monkeypatch.setattr(database, "get_supabase_client", lambda: SimpleNamespace(auth=FakeAuth()))
    monkeypatch.setattr(auth, "ensure_profile", lambda user_id, email: {"id": user_id, "email": email, "role": "admin"})
    auth.st.session_state.clear()

    profile = auth.restore_session()

    assert profile["role"] == "admin"
    assert auth.st.session_state["access_token"] == "new-access-token"
    assert auth._decode_refresh_token(manager.values[auth.SESSION_COOKIE_NAME]) == "new-refresh-token"


def test_sign_in_distinguishes_dns_error(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://abcdefghijklmnopqrst.supabase.co")

    class FakeAuth:
        def sign_in_with_password(self, _credentials):
            raise socket.gaierror(-2, "Name or service not known")

    class FakeClient:
        auth = FakeAuth()

    monkeypatch.setattr(database, "get_supabase_client", lambda: FakeClient())

    with pytest.raises(auth.AuthFlowError) as excinfo:
        auth.sign_in("user@example.com", "password")

    assert "DNS" in excinfo.value.user_message
    assert "abcdefghijklmnopqrst.supabase.co" in excinfo.value.guidance


def test_supabase_settings_rejects_placeholder_url(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://your-project-ref.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "real-anon-key")

    with pytest.raises(RuntimeError, match="サンプル値"):
        config.get_supabase_settings()


@pytest.mark.parametrize(
    ("url", "message"),
    [
        ("https://xxxxx.supabase.co", "project-ref"),
        ("https://supabase.com/dashboard/project/example", "Project URLだけ"),
        ("https://db.abcdefghijklmnopqrst.supabase.co", "Database接続用ホスト"),
        ("https://abcdefghijklmnopqrst.supabase.co/rest/v1", "Project URLだけ"),
        ("https://abcdefghijklmnopqrst.supabase.co?key=value", "Project URLだけ"),
    ],
)
def test_supabase_settings_rejects_non_project_urls(monkeypatch, url, message):
    monkeypatch.setenv("SUPABASE_URL", url)
    monkeypatch.setenv("SUPABASE_ANON_KEY", "real-anon-key")

    with pytest.raises(RuntimeError, match=message):
        config.get_supabase_settings()


def test_supabase_settings_accepts_project_url_with_wrapping_quotes(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", '"https://abcdefghijklmnopqrst.supabase.co/"')
    monkeypatch.setenv("SUPABASE_ANON_KEY", "real-anon-key")

    settings = config.get_supabase_settings()

    assert settings.url == "https://abcdefghijklmnopqrst.supabase.co"

