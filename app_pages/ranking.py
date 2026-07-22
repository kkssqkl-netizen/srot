from __future__ import annotations

from datetime import datetime, timedelta, timezone
from html import escape

import streamlit as st

import analyzer
from app_pages.common import filtered_data, require_data
from components import layout


JST = timezone(timedelta(hours=9))


def _diff_class(value) -> str:
    try:
        numeric = float(value)
    except Exception:
        return ""
    if numeric > 0:
        return "positive"
    if numeric < 0:
        return "negative"
    return ""


def _render_top_cards(ranking):
    cards = []
    for row in ranking.head(3).to_dict("records"):
        diff_value = row.get("期待差枚", 0)
        cards.append(
            f"""
            <div class="rank-card">
                <div class="rank-head">
                    <div class="rank-place">{escape(str(row.get("順位", "")))}位</div>
                    <div class="rank-machine-no">{escape(str(row.get("台番号", "")))}番台</div>
                </div>
                <div class="rank-machine">{escape(str(row.get("機種名", "")))}</div>
                <div class="rank-metrics">
                    <div class="rank-metric">
                        <div class="rank-metric-label">高設定期待度</div>
                        <div class="rank-metric-value">{escape(str(row.get("高設定期待度", 0)))}点</div>
                    </div>
                    <div class="rank-metric">
                        <div class="rank-metric-label">期待差枚</div>
                        <div class="rank-metric-value {_diff_class(diff_value)}">{layout.format_diff(diff_value)}</div>
                    </div>
                    <div class="rank-metric">
                        <div class="rank-metric-label">勝率</div>
                        <div class="rank-metric-value">{layout.format_rate(row.get("勝率", 0))}</div>
                    </div>
                    <div class="rank-metric">
                        <div class="rank-metric-label">信頼度</div>
                        <div class="rank-metric-value">{escape(str(row.get("信頼度", 0)))}点</div>
                    </div>
                </div>
                <div class="rank-reason">根拠: {escape(str(row.get("根拠", "")))}</div>
            </div>
            """
        )
    st.markdown(f'<div class="ranking-grid">{"".join(cards)}</div>', unsafe_allow_html=True)


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

    st.subheader("上位候補")
    _render_top_cards(ranking)

    st.subheader("一覧")
    st.dataframe(
        layout.style_diff_columns(ranking, ["期待差枚"]),
        use_container_width=True,
        hide_index=True,
        column_config=layout.table_column_config(ranking),
    )

    with st.expander("根拠の見方"):
        st.markdown(
            "- `X示唆` は入力した店長Xメモ内の機種名、台番号、末尾、ゾロ目などを反映します。\n"
            "- `直近上向き` は直近成績が過去平均より強い台です。\n"
            "- `前日/直近凹み` と `前々日まで凹み` は上げ狙いの材料です。\n"
            "- `曜日良好`、`特定日良好`、`平均G数高め` は過去データからの加点です。\n"
            "- `信頼度` はサンプル数と稼働量が多いほど上がります。"
        )

    st.caption("期待度は勝利保証ではなく、過去データと入力した示唆を使ったルールベース推定です。")
