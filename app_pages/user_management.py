from __future__ import annotations

import pandas as pd
import streamlit as st

import auth
import database
from config import VALID_ROLES


def render(df, calendar_df, profile):
    auth.require_admin()
    st.title("ユーザー管理")
    st.caption("権限変更は admin のみ実行できます。初回管理者は README の手順で作成してください。")

    try:
        profiles = database.list_profiles(st.session_state.get("access_token"))
    except Exception as exc:
        st.error("ユーザー一覧を取得できませんでした。")
        st.caption(str(exc))
        return

    profiles_df = pd.DataFrame(profiles)
    if profiles_df.empty:
        st.info("ユーザーがまだありません。")
        return

    st.dataframe(profiles_df, use_container_width=True, hide_index=True)
    user_options = {
        f"{row.get('email')} / {row.get('display_name')} / {row.get('role')}": row.get("id")
        for row in profiles
    }
    selected_label = st.selectbox("変更するユーザー", list(user_options.keys()))
    new_role = st.selectbox("新しい権限", list(VALID_ROLES))
    confirm = st.checkbox("権限変更を確認")
    if st.button("権限を変更", type="primary", disabled=not confirm, use_container_width=True):
        try:
            database.update_user_role(user_options[selected_label], new_role, st.session_state.get("access_token"))
            st.success("権限を変更しました。")
            auth.current_profile(refresh=True)
            st.rerun()
        except Exception as exc:
            st.error("権限変更に失敗しました。")
            st.caption(str(exc))

