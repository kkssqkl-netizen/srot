from __future__ import annotations

from datetime import date
from typing import Iterable

import pandas as pd
import streamlit as st

import auth
from analyzer import AnalysisFilters
from config import APP_NAME, ROLE_ADMIN, WEEKDAY_JP


def setup_page() -> None:
    st.set_page_config(page_title=APP_NAME, page_icon="📊", layout="wide", initial_sidebar_state="expanded")
    st.markdown(
        """
        <style>
        .block-container { padding-top: 1.4rem; padding-bottom: 3rem; }
        [data-testid="stMetric"] {
            background: #ffffff;
            border: 1px solid #e5e7eb;
            border-radius: 8px;
            padding: 0.7rem 0.8rem;
            box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04);
        }
        .small-note {
            color: #64748b;
            font-size: 0.86rem;
            line-height: 1.55;
        }
        .danger-note {
            background: #fff7ed;
            border: 1px solid #fed7aa;
            border-radius: 8px;
            padding: 0.7rem 0.85rem;
            color: #9a3412;
        }
        .role-badge {
            display: inline-block;
            padding: 0.15rem 0.5rem;
            border-radius: 999px;
            background: #e0f2fe;
            color: #075985;
            font-size: 0.78rem;
            font-weight: 600;
        }
        div[data-testid="stDataFrame"] { width: 100%; }
        @media (max-width: 640px) {
            .block-container { padding-left: 0.85rem; padding-right: 0.85rem; }
            [data-testid="stMetric"] { padding: 0.55rem 0.6rem; }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_sidebar(profile: dict) -> str:
    st.sidebar.title("分析メニュー")
    role = profile.get("role", "viewer")
    user = st.session_state.get("user", {})
    st.sidebar.caption(user.get("email", ""))
    st.sidebar.markdown(f'<span class="role-badge">{role}</span>', unsafe_allow_html=True)

    pages = [
        "ダッシュボード",
        "狙い台ランキング",
        "台別分析",
        "機種別分析",
        "店舗傾向",
    ]
    if role == ROLE_ADMIN:
        pages.extend(["管理画面", "ユーザー管理"])

    selected = st.sidebar.radio("画面", pages, label_visibility="collapsed")
    st.sidebar.divider()
    if st.sidebar.button("ログアウト", use_container_width=True):
        auth.sign_out()
        st.rerun()
    return selected


def render_disclaimer() -> None:
    st.markdown(
        '<div class="danger-note">分析結果は過去データに基づく推定であり、高設定投入や勝利を保証するものではありません。'
        "実戦判断はご自身の責任で行ってください。</div>",
        unsafe_allow_html=True,
    )


def format_diff(value: float | int | None) -> str:
    if value is None or pd.isna(value):
        return "0枚"
    value = float(value)
    sign = "+" if value > 0 else ""
    return f"{sign}{value:,.0f}枚"


def format_rate(value: float | int | None) -> str:
    if value is None or pd.isna(value):
        return "0%"
    return f"{float(value):.0f}%"


def render_filter_panel(df: pd.DataFrame, key_prefix: str, show_machine_filters: bool = True) -> AnalysisFilters:
    st.sidebar.subheader("分析条件")
    if df.empty:
        return AnalysisFilters()

    min_date = df["date"].min().date()
    max_date = df["date"].max().date()
    period = st.sidebar.date_input(
        "対象期間",
        value=(min_date, max_date),
        min_value=min_date,
        max_value=max_date,
        key=f"{key_prefix}_period",
    )
    if isinstance(period, tuple) and len(period) == 2:
        start_date, end_date = period
    else:
        start_date, end_date = min_date, max_date

    min_games = st.sidebar.number_input("最低ゲーム数", min_value=0, max_value=20000, value=0, step=100, key=f"{key_prefix}_min_games")
    recent_days = st.sidebar.slider("直近重視日数", min_value=3, max_value=60, value=14, key=f"{key_prefix}_recent_days")

    machine_name = None
    machine_no = None
    if show_machine_filters:
        machine_names = ["すべて"] + sorted(df["machine_name"].dropna().astype(str).unique().tolist())
        selected_machine_name = st.sidebar.selectbox("機種名フィルター", machine_names, key=f"{key_prefix}_machine_name")
        if selected_machine_name != "すべて":
            machine_name = selected_machine_name

        machine_no_text = st.sidebar.text_input("台番号フィルター", key=f"{key_prefix}_machine_no")
        if machine_no_text.strip():
            try:
                machine_no = int(machine_no_text.strip())
            except ValueError:
                st.sidebar.warning("台番号は数字で入力してください。")

    weekday_options = list(WEEKDAY_JP.values())
    weekdays = st.sidebar.multiselect("曜日", weekday_options, default=[], key=f"{key_prefix}_weekdays")
    special_only = st.sidebar.checkbox("特定日のみ", value=False, key=f"{key_prefix}_special_only")
    limit = st.sidebar.slider("表示件数", min_value=5, max_value=100, value=20, step=5, key=f"{key_prefix}_limit")

    return AnalysisFilters(
        start_date=start_date,
        end_date=end_date,
        min_games=int(min_games),
        recent_days=int(recent_days),
        machine_name=machine_name,
        machine_no=machine_no,
        weekdays=weekdays,
        special_only=special_only,
        limit=int(limit),
    )


def style_diff_columns(df: pd.DataFrame, diff_columns: Iterable[str]):
    def color(value):
        try:
            numeric = float(value)
        except Exception:
            return ""
        if numeric > 0:
            return "color: #dc2626; font-weight: 700;"
        if numeric < 0:
            return "color: #2563eb; font-weight: 700;"
        return "color: #475569;"

    numeric_formats = {
        col: "{:,.0f}"
        for col in df.columns
        if pd.api.types.is_numeric_dtype(df[col]) and not pd.api.types.is_bool_dtype(df[col])
    }
    return df.style.map(color, subset=[col for col in diff_columns if col in df.columns]).format(numeric_formats)
