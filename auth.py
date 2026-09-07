"""Supabase Auth helpers and role checks for Streamlit."""

from __future__ import annotations

import socket
from typing import Any

import streamlit as st

from config import ROLE_ADMIN, ROLE_VIEWER, VALID_ROLES, get_admin_emails, get_configured_supabase_host
import database


PERMISSIONS: dict[str, set[str]] = {
    ROLE_ADMIN: {
        "view_analysis",
        "import_data",
        "edit_data",
        "delete_data",
        "manage_users",
        "view_logs",
        "export_csv",
        "import_csv",
    },
    ROLE_VIEWER: {"view_analysis"},
}


class AuthFlowError(RuntimeError):
    """User-facing error raised during login/signup flows."""

    def __init__(self, user_message: str, detail: str = "", guidance: str = "") -> None:
        super().__init__(detail or user_message)
        self.user_message = user_message
        self.detail = detail
        self.guidance = guidance


def _exception_chain(exc: BaseException) -> list[BaseException]:
    chain: list[BaseException] = []
    current: BaseException | None = exc
    seen: set[int] = set()
    while current and id(current) not in seen:
        chain.append(current)
        seen.add(id(current))
        current = current.__cause__ or current.__context__
    return chain


def _exception_detail(exc: BaseException) -> str:
    return " / ".join(f"{type(item).__name__}: {item}" for item in _exception_chain(exc))


def _exception_text(exc: BaseException) -> str:
    return _exception_detail(exc).lower()


def _exception_status_code(exc: BaseException) -> int | None:
    for item in _exception_chain(exc):
        for attr in ("status_code", "code"):
            value = getattr(item, attr, None)
            if isinstance(value, int):
                return value
            if isinstance(value, str) and value.isdigit():
                return int(value)
        response = getattr(item, "response", None)
        value = getattr(response, "status_code", None)
        if isinstance(value, int):
            return value
    return None


def _connection_or_config_error(exc: BaseException) -> AuthFlowError | None:
    detail = _exception_detail(exc)
    text = detail.lower()
    chain = _exception_chain(exc)

    if "パッケージがインストールされていません" in text or "no module named" in text:
        return AuthFlowError(
            "必要なPythonパッケージが不足しています。",
            detail,
            "requirements.txt に supabase が含まれていること、Streamlit Cloud で依存関係のインストールが成功していることを確認してください。",
        )

    if "supabase_" in text or "streamlit secrets" in text or "サンプル値" in text or "形式が不正" in text:
        return AuthFlowError(
            "Supabase設定に問題があります。",
            detail,
            "Streamlit Secrets の SUPABASE_URL / SUPABASE_ANON_KEY / SUPABASE_SERVICE_ROLE_KEY を確認してください。",
        )

    if any(isinstance(item, socket.gaierror) for item in chain) or any(
        marker in text
        for marker in (
            "name or service not known",
            "temporary failure in name resolution",
            "nodename nor servname provided",
            "getaddrinfo failed",
            "nameresolutionerror",
        )
    ):
        configured_host = get_configured_supabase_host()
        return AuthFlowError(
            "Supabaseに接続できませんでした（DNS/URL解決エラー）。",
            detail,
            f"現在の接続先は `{configured_host}` です。Supabase DashboardのProject URLと完全に一致するか確認してください。",
        )

    if any(isinstance(item, (TimeoutError, ConnectionError)) for item in chain) or any(
        marker in text
        for marker in (
            "connecterror",
            "connection refused",
            "connection reset",
            "network is unreachable",
            "timed out",
            "timeout",
            "all connection attempts failed",
            "certificate verify failed",
        )
    ):
        return AuthFlowError(
            "Supabaseに接続できませんでした（ネットワークエラー）。",
            detail,
            "一時的な通信障害、Supabaseプロジェクト停止、または Streamlit Cloud から Supabase への到達性を確認してください。",
        )

    return None


def _classify_sign_in_error(exc: BaseException) -> AuthFlowError:
    connection_error = _connection_or_config_error(exc)
    if connection_error:
        return connection_error

    text = _exception_text(exc)
    status_code = _exception_status_code(exc)

    if "email not confirmed" in text or "email_not_confirmed" in text:
        return AuthFlowError(
            "メール認証が完了していない可能性があります。",
            _exception_detail(exc),
            "Supabase Authentication の対象ユーザーで Confirmed が有効になっているか確認してください。",
        )

    if status_code in {400, 401, 403} or any(
        marker in text
        for marker in (
            "invalid login credentials",
            "invalid credentials",
            "invalid email or password",
            "invalid_grant",
        )
    ):
        return AuthFlowError(
            "認証に失敗しました。メールアドレスとパスワードを確認してください。",
            _exception_detail(exc),
        )

    return AuthFlowError("ログイン処理中に予期しないエラーが発生しました。", _exception_detail(exc))


def _classify_profile_error(exc: BaseException) -> AuthFlowError:
    connection_error = _connection_or_config_error(exc)
    if connection_error:
        return connection_error

    return AuthFlowError(
        "ログインは成功しましたが、プロフィール情報の取得または作成に失敗しました。",
        _exception_detail(exc),
        "Supabase SQL Editor で sql/001_schema.sql が実行済みか、profiles テーブルと RLS ポリシーを確認してください。",
    )


def can(role: str | None, action: str) -> bool:
    return action in PERMISSIONS.get(role or "", set())


def is_admin(profile: dict[str, Any] | None = None) -> bool:
    profile = profile or st.session_state.get("profile")
    return bool(profile and profile.get("role") == ROLE_ADMIN)


def _store_session(auth_response: Any) -> None:
    session = auth_response.session
    user = auth_response.user
    st.session_state["access_token"] = session.access_token
    st.session_state["refresh_token"] = session.refresh_token
    st.session_state["user"] = {
        "id": user.id,
        "email": user.email,
    }


def ensure_profile(user_id: str, email: str) -> dict[str, Any]:
    """Create or refresh the user's profile.

    Initial admin bootstrap is intentionally explicit: set APP_ADMIN_EMAILS in
    secrets, sign in once, and the matching user is assigned admin by the
    server-side service client when available.
    """

    bootstrap_admin = email.lower() in get_admin_emails()
    role = ROLE_ADMIN if bootstrap_admin else ROLE_VIEWER
    profile = database.ensure_profile(
        user_id=user_id,
        email=email,
        display_name=email.split("@")[0],
        requested_role=role,
        access_token=st.session_state.get("access_token"),
    )
    st.session_state["profile"] = profile
    return profile


def sign_in(email: str, password: str) -> dict[str, Any]:
    try:
        client = database.get_supabase_client()
        response = client.auth.sign_in_with_password({"email": email, "password": password})
    except Exception as exc:
        raise _classify_sign_in_error(exc) from exc

    try:
        _store_session(response)
    except Exception as exc:
        raise AuthFlowError("Supabase Authのログイン応答を処理できませんでした。", _exception_detail(exc)) from exc
    try:
        return ensure_profile(response.user.id, response.user.email or email)
    except Exception as exc:
        raise _classify_profile_error(exc) from exc


def sign_up(email: str, password: str, display_name: str = "") -> dict[str, Any]:
    try:
        client = database.get_supabase_client()
        response = client.auth.sign_up(
            {
                "email": email,
                "password": password,
                "options": {"data": {"display_name": display_name or email.split("@")[0]}},
            }
        )
    except Exception as exc:
        connection_error = _connection_or_config_error(exc)
        if connection_error:
            raise connection_error from exc
        raise AuthFlowError("ユーザー作成に失敗しました。", _exception_detail(exc)) from exc

    if response.session:
        try:
            _store_session(response)
        except Exception as exc:
            raise AuthFlowError("Supabase Authのユーザー作成応答を処理できませんでした。", _exception_detail(exc)) from exc
        try:
            return ensure_profile(response.user.id, response.user.email or email)
        except Exception as exc:
            raise _classify_profile_error(exc) from exc
    return {"email": email, "role": ROLE_VIEWER, "pending_confirmation": True}


def sign_out() -> None:
    for key in ("access_token", "refresh_token", "user", "profile", "import_preview"):
        st.session_state.pop(key, None)
    try:
        database.get_supabase_client().auth.sign_out()
    except Exception:
        pass


def current_profile(refresh: bool = False) -> dict[str, Any] | None:
    if not st.session_state.get("access_token") or not st.session_state.get("user"):
        return None
    if refresh or "profile" not in st.session_state:
        user = st.session_state["user"]
        profile = database.get_profile(user["id"], st.session_state["access_token"])
        if profile:
            st.session_state["profile"] = profile
    return st.session_state.get("profile")


def render_login() -> None:
    st.title("ログイン")
    st.caption("URLを知っているだけでは閲覧できません。登録済みユーザーでログインしてください。")

    tab_login, tab_signup = st.tabs(["ログイン", "新規ユーザー作成"])

    with tab_login:
        with st.form("login_form"):
            email = st.text_input("メールアドレス")
            password = st.text_input("パスワード", type="password")
            submitted = st.form_submit_button("ログイン", type="primary")
        if submitted:
            try:
                profile = sign_in(email.strip(), password)
                st.success(f"ログインしました（権限: {profile.get('role', ROLE_VIEWER)}）")
                st.rerun()
            except AuthFlowError as exc:
                st.error(exc.user_message)
                if exc.guidance:
                    st.warning(exc.guidance)
                if exc.detail:
                    st.caption(exc.detail)
            except Exception as exc:
                st.error("ログイン処理中に予期しないエラーが発生しました。")
                st.caption(str(exc))

    with tab_signup:
        st.info("新規ユーザーは viewer として作成されます。管理者への変更は管理者画面から行います。")
        with st.form("signup_form"):
            display_name = st.text_input("表示名")
            email = st.text_input("メールアドレス", key="signup_email")
            password = st.text_input("パスワード", type="password", key="signup_password")
            submitted = st.form_submit_button("ユーザー作成")
        if submitted:
            try:
                profile = sign_up(email.strip(), password, display_name.strip())
                if profile.get("pending_confirmation"):
                    st.success("確認メールを送信しました。メール認証後にログインしてください。")
                else:
                    st.success("ユーザーを作成しました。")
                    st.rerun()
            except AuthFlowError as exc:
                st.error(exc.user_message)
                if exc.guidance:
                    st.warning(exc.guidance)
                if exc.detail:
                    st.caption(exc.detail)
            except Exception as exc:
                st.error("ユーザー作成に失敗しました。")
                st.warning("SupabaseのSQL未実行、Secrets設定ミス、またはAuthenticationのEmail provider無効が主な原因です。")
                st.code(str(exc))


def require_login() -> dict[str, Any]:
    profile = current_profile(refresh=False)
    if profile:
        return profile
    render_login()
    st.stop()


def require_admin() -> dict[str, Any]:
    profile = require_login()
    if not can(profile.get("role"), "manage_users") and not can(profile.get("role"), "import_data"):
        st.error("権限不足です。管理者のみ利用できます。")
        st.stop()
    return profile

