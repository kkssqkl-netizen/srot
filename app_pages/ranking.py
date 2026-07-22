from __future__ import annotations

from datetime import datetime, timedelta, timezone

import plotly.express as px
import streamlit as st

import analyzer
from app_pages.common import filtered_data, require_data
from components import layout


JST = timezone(timedelta(hours=9))


def render(df, calendar_df, profile):
    st.title("狙い台ランキング")
    layout.render_disclaimer()
    if not require_data(df):
        return

    filtered, filters = filtered_data(df, "ranking")
    st.subheader("店に行く日の期待度")
    target_date = st.date_input("店に行く日", value=datetime.now(JST).date(), key="ranking_target_visit_date")
    hint_text = st.text_area(
        "店長X示唆メモ（任意）",
        placeholder="Xの投稿文や示唆を貼ってください。例: 末尾7 / 北斗 / 545番台 / ゾロ目 など",
        height=110,
        key="ranking_x_hint_text",
    )
    context = analyzer.target_day_context(target_date, calendar_df, hint_text)
    special_label = "特定日" if context["special_day"] else "通常日"
    st.caption(f"予測対象: {target_date}（{context['weekday']}） / {special_label}。Xは自動取得せず、貼り付けた示唆だけを使います。")
    if context["event_name"] or context["memo"]:
        st.caption(f"登録済みメモ: {context['event_name']} {context['memo']}".strip())

    ranking = analyzer.calculate_target_ranking(
        filtered,
        recent_days=filters.recent_days,
        limit=filters.limit,
        target_date=target_date,
        calendar_df=calendar_df,
        hint_text=hint_text,
    )
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
        title=f"{target_date} の高設定期待度スコア",
        labels=layout.COLUMN_LABELS,
    )
    st.plotly_chart(fig, use_container_width=True)
    st.dataframe(layout.style_diff_columns(ranking, ["期待差枚"]), use_container_width=True, hide_index=True)

    st.caption("スコアは対象日の曜日、特定日、店長X示唆メモ、差枚、G数、直近成績、前日・前々日、機種傾向、サンプル数を使ったルールベース推定です。")
