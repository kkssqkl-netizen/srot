from __future__ import annotations

import streamlit as st

import auth
from app_pages import admin, dashboard, machine_detail, model_detail, ranking, store_trends, user_management
from components import layout
from config import APP_NAME
from services import data_service


def main() -> None:
    layout.setup_page()

    profile = auth.current_profile(refresh=False)
    if not profile:
        auth.render_login()
        return

    selected = layout.render_sidebar(profile)

    try:
        df, calendar_df = data_service.load_prepared_data(st.session_state["access_token"])
    except Exception as exc:
        st.title(APP_NAME)
        st.error("Supabaseに接続できませんでした。Secrets設定とSQL適用状況を確認してください。")
        st.caption(str(exc))
        return

    if selected == "ダッシュボード":
        dashboard.render(df, calendar_df, profile)
    elif selected == "狙い台ランキング":
        ranking.render(df, calendar_df, profile)
    elif selected == "台別分析":
        machine_detail.render(df, calendar_df, profile)
    elif selected == "機種別分析":
        model_detail.render(df, calendar_df, profile)
    elif selected == "店舗傾向":
        store_trends.render(df, calendar_df, profile)
    elif selected == "管理画面":
        admin.render(df, calendar_df, profile)
    elif selected == "ユーザー管理":
        user_management.render(df, calendar_df, profile)


if __name__ == "__main__":
    main()

