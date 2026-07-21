from __future__ import annotations

import plotly.express as px
import streamlit as st

import analyzer
from app_pages.common import filtered_data, require_data
from components import layout


def render(df, calendar_df, profile):
    st.title("機種別分析")
    layout.render_disclaimer()
    if not require_data(df):
        return

    filtered, _filters = filtered_data(df, "model_detail", show_machine_filters=False)
    machine_names = sorted(filtered["machine_name"].dropna().astype(str).unique().tolist())
    if not machine_names:
        st.warning("条件に一致する機種がありません。")
        return

    selected = st.selectbox("機種名", machine_names)
    detail = analyzer.model_detail(filtered, selected)
    group = detail["data"]

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("設置台数", f"{detail['machines']:,}台")
    c2.metric("平均ゲーム数", f"{detail['avg_games']:,.0f}G")
    c3.metric("平均差枚", layout.format_diff(detail["avg_diff"]))
    c4.metric("勝率", layout.format_rate(detail["win_rate"]))

    tab_machine, tab_daily, tab_special = st.tabs(["台番号別", "日付別", "特定日"])
    with tab_machine:
        fig = px.bar(detail["by_machine"], x="machine_no", y="avg_diff", color="avg_diff", color_continuous_scale=["#2563eb", "#f8fafc", "#dc2626"], title="台番号別成績")
        st.plotly_chart(fig, use_container_width=True)
        st.dataframe(layout.style_diff_columns(detail["by_machine"], ["avg_diff"]), use_container_width=True, hide_index=True)
        c1, c2 = st.columns(2)
        with c1:
            st.subheader("強い台番号")
            st.dataframe(layout.style_diff_columns(detail["strong_machines"], ["avg_diff"]), use_container_width=True, hide_index=True)
        with c2:
            st.subheader("弱い台番号")
            st.dataframe(layout.style_diff_columns(detail["weak_machines"], ["avg_diff"]), use_container_width=True, hide_index=True)
    with tab_daily:
        st.dataframe(layout.style_diff_columns(detail["daily"], ["total_diff", "avg_diff"]), use_container_width=True, hide_index=True)
        fig_daily = px.line(detail["daily"], x="date", y=["total_diff", "avg_diff"], markers=True, title="日付別成績")
        st.plotly_chart(fig_daily, use_container_width=True)
    with tab_special:
        st.dataframe(layout.style_diff_columns(detail["special"], ["avg_diff"]), use_container_width=True, hide_index=True)

