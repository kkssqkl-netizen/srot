from __future__ import annotations

import pandas as pd
import streamlit as st

import analyzer
from components import layout


def require_data(df: pd.DataFrame) -> bool:
    if not df.empty:
        return True
    st.info("まだ分析データがありません。管理者がana-slo日別URLまたは保存HTMLからデータを登録すると表示されます。")
    return False


def filtered_data(df: pd.DataFrame, key_prefix: str, show_machine_filters: bool = True):
    filters = layout.render_filter_panel(df, key_prefix=key_prefix, show_machine_filters=show_machine_filters)
    return analyzer.apply_filters(df, filters), filters

