from __future__ import annotations

import plotly.express as px
import streamlit as st

import analyzer
from app_pages.common import filtered_data, require_data
from components import layout


def render(df, calendar_df, profile):
    st.title("狙い台ランキング")
    layout.render_disclaimer()
    if not require_data(df):
        return

    filtered, filters = filtered_data(df, "ranking")
    ranking = analyzer.calculate_target_ranking(filtered, recent_days=filters.recent_days, limit=filters.limit)
    if ranking.empty:
        st.warning("条件に一致するデータがありません。")
        return

    fig = px.bar(
        ranking.sort_values("高設定期待度"),
        x="高設定期待度",
        y="台番号",
        orientation="h",
        color="期待差枚",
        color_continuous_scale=["#2563eb", "#f8fafc", "#dc2626"],
        title="高設定期待度スコア",
    )
    st.plotly_chart(fig, use_container_width=True)
    st.dataframe(layout.style_diff_columns(ranking, ["期待差枚"]), use_container_width=True, hide_index=True)

    st.caption("スコアは差枚、G数、直近成績、曜日、特定日、台番号傾向、前日・前々日、機種傾向、サンプル数を使ったルールベース推定です。")

