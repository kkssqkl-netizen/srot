from __future__ import annotations

import plotly.express as px
import streamlit as st

import analyzer
from app_pages.common import filtered_data, require_data
from components import layout


def render(df, calendar_df, profile):
    st.title("店舗傾向")
    layout.render_disclaimer()
    if not require_data(df):
        return

    filtered, filters = filtered_data(df, "store_trends")
    daily = analyzer.daily_trends(filtered)
    weekday = analyzer.weekday_trends(filtered)
    special = analyzer.special_day_trends(filtered)
    model = analyzer.machine_name_trends(filtered)

    tab_day, tab_weekday, tab_special, tab_model = st.tabs(["日別", "曜日別", "特定日別", "機種別"])
    with tab_day:
        fig = px.bar(daily, x="date", y="avg_diff", color="avg_diff", color_continuous_scale=["#2563eb", "#f8fafc", "#dc2626"], title="日別平均差枚")
        st.plotly_chart(fig, use_container_width=True)
        st.dataframe(layout.style_diff_columns(daily, ["total_diff", "avg_diff"]), use_container_width=True, hide_index=True)
    with tab_weekday:
        fig = px.bar(weekday, x="weekday", y="avg_diff", color="win_rate", title="曜日別傾向")
        st.plotly_chart(fig, use_container_width=True)
        st.dataframe(layout.style_diff_columns(weekday, ["avg_diff"]), use_container_width=True, hide_index=True)
    with tab_special:
        special_display = special.replace({"special_day": {True: "特定日", False: "通常日"}})
        st.dataframe(layout.style_diff_columns(special_display, ["avg_diff"]), use_container_width=True, hide_index=True)
    with tab_model:
        st.dataframe(layout.style_diff_columns(model.head(filters.limit), ["avg_diff"]), use_container_width=True, hide_index=True)

