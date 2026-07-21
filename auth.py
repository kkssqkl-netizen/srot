"""Supabase Auth helpers and role checks for Streamlit."""

from __future__ import annotations

from typing import Any

import streamlit as st

from config import ROLE_ADMIN, ROLE_VIEWER, VALID_ROLES, get_admin_emails
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
    client = database.get_supabase_client()
    response = client.auth.sign_in_with_password({"email": email, "password": password})
    _store_session(response)
    return ensure_profile(response.user.id, response.user.email or email)


def sign_up(email: str, password: str, display_name: str = "") -> dict[str, Any]:
    client = database.get_supabase_client()
    response = client.auth.sign_up(
        {
            "email": email,
            "password": password,
            "options": {"data": {"display_name": display_name or email.split("@")[0]}},
        }
    )
    if response.session:
        _store_session(response)
        return ensure_profile(response.user.id, response.user.email or email)
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
            except Exception as exc:
                st.error("ログインできませんでした。メールアドレスとパスワードを確認してください。")
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
