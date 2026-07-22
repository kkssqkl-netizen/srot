from __future__ import annotations

import plotly.express as px
import streamlit as st

import analyzer
from app_pages.common import filtered_data, require_data
from components import layout


def render(df, calendar_df, profile):
    st.title("台別分析")
    layout.render_disclaimer()
    if not require_data(df):
        return

    filtered, _filters = filtered_data(df, "machine_detail", show_machine_filters=False)
    machine_numbers = sorted(filtered["machine_no"].dropna().astype(int).unique().tolist())
    if not machine_numbers:
        st.warning("条件に一致する台番号がありません。")
        return

    selected = st.selectbox("台番号", machine_numbers)
    detail = analyzer.machine_detail(filtered, int(selected))
    group = detail["data"]
    if group.empty:
        st.warning("データがありません。")
        return

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("勝率", layout.format_rate(detail["win_rate"]))
    c2.metric("平均差枚", layout.format_diff(detail["avg_diff"]))
    c3.metric("中央値差枚", layout.format_diff(detail["median_diff"]))
    c4.metric("最大差枚", layout.format_diff(detail["max_diff"]))
    c5.metric("最小差枚", layout.format_diff(detail["min_diff"]))

    tab_daily, tab_recent, tab_pattern = st.tabs(["日付別", "直近", "傾向"])
    with tab_daily:
        fig = px.bar(group, x="date", y="diff_coins", color="diff_coins", color_continuous_scale=["#2563eb", "#f8fafc", "#dc2626"], title=f"{selected}番台 日付別差枚", labels=layout.COLUMN_LABELS)
        st.plotly_chart(fig, use_container_width=True)
        fig_games = px.line(group, x="date", y="games", markers=True, title="日付別ゲーム数", labels=layout.COLUMN_LABELS)
        st.plotly_chart(fig_games, use_container_width=True)
        display = group[["date", "machine_name", "games", "diff_coins", "bb", "rb", "at_hits", "first_hits", "special_day", "event_name"]]
        st.dataframe(layout.style_diff_columns(display, ["diff_coins"]), use_container_width=True, hide_index=True)

    with tab_recent:
        c1, c2, c3 = st.columns(3)
        c1.metric("直近7日 平均差枚", layout.format_diff(detail["last_7"]["diff_coins"].mean()))
        c2.metric("直近14日 平均差枚", layout.format_diff(detail["last_14"]["diff_coins"].mean()))
        c3.metric("直近30日 平均差枚", layout.format_diff(detail["last_30"]["diff_coins"].mean()))
        fig_trend = px.line(group, x="date", y="expectation_trend", markers=True, title="高設定期待度の推移", labels=layout.COLUMN_LABELS)
        st.plotly_chart(fig_trend, use_container_width=True)

    with tab_pattern:
        st.subheader("特定日・曜日別成績")
        st.dataframe(layout.style_diff_columns(detail["special"], ["diff_coins"]), use_container_width=True, hide_index=True)
        st.dataframe(layout.style_diff_columns(detail["weekday"], ["avg_diff"]), use_container_width=True, hide_index=True)
        st.subheader("前日・前々日差枚との関係")
        c1, c2 = st.columns(2)
        c1.metric("前日差枚との相関", "N/A" if detail["prev_corr"] != detail["prev_corr"] else f"{detail['prev_corr']:.2f}")
        c2.metric("前々日差枚との相関", "N/A" if detail["prev2_corr"] != detail["prev2_corr"] else f"{detail['prev2_corr']:.2f}")
        fig_prev = px.scatter(group.dropna(subset=["prev_diff"]), x="prev_diff", y="diff_coins", trendline="ols", title="前日差枚 vs 当日差枚", labels=layout.COLUMN_LABELS)
        st.plotly_chart(fig_prev, use_container_width=True)
