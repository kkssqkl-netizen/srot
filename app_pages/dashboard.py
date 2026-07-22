from __future__ import annotations

import plotly.express as px
import streamlit as st

import analyzer
from app_pages.common import filtered_data, require_data
from components import layout


def render(df, calendar_df, profile):
    st.title("ダッシュボード")
    layout.render_disclaimer()
    if not require_data(df):
        return

    filtered, filters = filtered_data(df, "dashboard")
    summary = analyzer.store_summary(filtered)

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("保存済みデータ件数", f"{summary['records']:,}")
    c2.metric("対象日数", f"{summary['days']:,}日")
    c3.metric("対象台数", f"{summary['machines']:,}台")
    c4.metric("店舗平均差枚", layout.format_diff(summary["avg_diff"]))
    c5.metric("店舗勝率", layout.format_rate(summary["win_rate"]))

    daily = analyzer.daily_trends(filtered)
    model = analyzer.machine_name_trends(filtered)

    tab_daily, tab_model, tab_recent = st.tabs(["日別傾向", "機種別傾向", "直近ランキング"])
    with tab_daily:
        if not daily.empty:
            fig = px.bar(
                daily,
                x="date",
                y="total_diff",
                title="日別総差枚",
                color="total_diff",
                color_continuous_scale=["#2563eb", "#f8fafc", "#dc2626"],
                labels=layout.COLUMN_LABELS,
            )
            st.plotly_chart(fig, use_container_width=True)
            st.dataframe(layout.style_diff_columns(daily, ["total_diff", "avg_diff"]), use_container_width=True, hide_index=True)
    with tab_model:
        st.dataframe(layout.style_diff_columns(model.head(filters.limit), ["avg_diff"]), use_container_width=True, hide_index=True)
    with tab_recent:
        ranking = analyzer.calculate_target_ranking(filtered, recent_days=filters.recent_days, limit=filters.limit)
        st.dataframe(layout.style_diff_columns(ranking, ["期待差枚"]), use_container_width=True, hide_index=True)
