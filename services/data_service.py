"""Data loading helpers used by Streamlit pages."""

from __future__ import annotations

import pandas as pd
import streamlit as st

import analyzer
from config import STORE_NAME
import database


@st.cache_data(ttl=60, show_spinner=False)
def load_machine_records(access_token: str) -> pd.DataFrame:
    rows = database.fetch_machine_records(access_token=access_token, store_name=STORE_NAME)
    return database.records_to_dataframe(rows)


@st.cache_data(ttl=60, show_spinner=False)
def load_calendar(access_token: str) -> pd.DataFrame:
    rows = database.fetch_store_calendar(access_token=access_token, store_name=STORE_NAME)
    return pd.DataFrame(rows)


def load_prepared_data(access_token: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    records_df = load_machine_records(access_token)
    calendar_df = load_calendar(access_token)
    prepared = analyzer.prepare_dataframe(records_df, calendar_df)
    return prepared, calendar_df


def clear_data_cache() -> None:
    load_machine_records.clear()
    load_calendar.clear()

