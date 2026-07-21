"""Rule-based analysis for machine targeting.

This module deliberately avoids Streamlit imports so it can be tested and later
replaced with a model-based scorer.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

import numpy as np
import pandas as pd

from config import STORE_NAME, WEEKDAY_JP


@dataclass(frozen=True)
class AnalysisFilters:
    start_date: date | None = None
    end_date: date | None = None
    min_games: int = 0
    recent_days: int = 14
    machine_name: str | None = None
    machine_no: int | None = None
    weekdays: list[str] | None = None
    special_only: bool = False
    limit: int = 20


def prepare_dataframe(df: pd.DataFrame, calendar_df: pd.DataFrame | None = None) -> pd.DataFrame:
    df = df.copy()
    if df.empty:
        return df

    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date"])
    for col in ["machine_no", "games", "diff_coins", "bb", "rb", "at_hits", "first_hits"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)
    df["win"] = df["diff_coins"] > 0
    df["weekday"] = df["date"].dt.weekday.map(WEEKDAY_JP)
    df["date_only"] = df["date"].dt.date
    if "special_day" not in df.columns:
        df["special_day"] = False
    df["special_day"] = df["special_day"].fillna(False).astype(bool)

    if calendar_df is not None and not calendar_df.empty:
        cal = calendar_df.copy()
        cal["date"] = pd.to_datetime(cal["date"], errors="coerce").dt.date
        cal = cal.dropna(subset=["date"])
        cal = cal[["date", "special_day", "event_name", "memo"]].rename(
            columns={"special_day": "calendar_special_day"}
        )
        df = df.merge(cal, left_on="date_only", right_on="date", how="left", suffixes=("", "_cal"))
        df["special_day"] = df["calendar_special_day"].combine_first(df["special_day"]).fillna(False).astype(bool)
        for text_col in ["event_name", "memo"]:
            if text_col not in df.columns:
                df[text_col] = ""
            else:
                df[text_col] = df[text_col].fillna("")
        df = df.drop(columns=[col for col in ["date_cal", "calendar_special_day"] if col in df.columns])
    else:
        df["event_name"] = ""
        df["memo"] = ""

    return df


def apply_filters(df: pd.DataFrame, filters: AnalysisFilters) -> pd.DataFrame:
    if df.empty:
        return df
    out = df.copy()
    if filters.start_date:
        out = out[out["date"].dt.date >= filters.start_date]
    if filters.end_date:
        out = out[out["date"].dt.date <= filters.end_date]
    if filters.min_games:
        out = out[out["games"] >= filters.min_games]
    if filters.machine_name:
        out = out[out["machine_name"].astype(str).str.contains(filters.machine_name, case=False, na=False)]
    if filters.machine_no:
        out = out[out["machine_no"] == int(filters.machine_no)]
    if filters.weekdays:
        out = out[out["weekday"].isin(filters.weekdays)]
    if filters.special_only:
        out = out[out["special_day"]]
    return out


def store_summary(df: pd.DataFrame) -> dict[str, Any]:
    if df.empty:
        return {
            "records": 0,
            "days": 0,
            "machines": 0,
            "avg_diff": 0,
            "win_rate": 0.0,
            "total_diff": 0,
            "avg_games": 0,
        }
    return {
        "records": int(len(df)),
        "days": int(df["date_only"].nunique()),
        "machines": int(df["machine_no"].nunique()),
        "avg_diff": float(df["diff_coins"].mean()),
        "win_rate": float(df["win"].mean() * 100),
        "total_diff": int(df["diff_coins"].sum()),
        "avg_games": float(df["games"].mean()),
    }


def daily_trends(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=["date", "total_diff", "avg_diff", "win_rate", "avg_games", "machines"])
    grouped = (
        df.groupby("date_only")
        .agg(
            total_diff=("diff_coins", "sum"),
            avg_diff=("diff_coins", "mean"),
            win_rate=("win", lambda s: s.mean() * 100),
            avg_games=("games", "mean"),
            machines=("machine_no", "nunique"),
        )
        .reset_index()
        .rename(columns={"date_only": "date"})
    )
    return grouped.sort_values("date")


def weekday_trends(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=["weekday", "avg_diff", "win_rate", "avg_games", "samples"])
    order = ["月", "火", "水", "木", "金", "土", "日"]
    out = (
        df.groupby("weekday")
        .agg(
            avg_diff=("diff_coins", "mean"),
            win_rate=("win", lambda s: s.mean() * 100),
            avg_games=("games", "mean"),
            samples=("machine_no", "count"),
        )
        .reset_index()
    )
    out["weekday"] = pd.Categorical(out["weekday"], order, ordered=True)
    return out.sort_values("weekday")


def special_day_trends(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=["special_day", "avg_diff", "win_rate", "avg_games", "samples"])
    return (
        df.groupby("special_day")
        .agg(
            avg_diff=("diff_coins", "mean"),
            win_rate=("win", lambda s: s.mean() * 100),
            avg_games=("games", "mean"),
            samples=("machine_no", "count"),
        )
        .reset_index()
    )


def machine_name_trends(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=["machine_name", "machines", "avg_games", "avg_diff", "win_rate", "samples"])
    return (
        df.groupby("machine_name")
        .agg(
            machines=("machine_no", "nunique"),
            avg_games=("games", "mean"),
            avg_diff=("diff_coins", "mean"),
            win_rate=("win", lambda s: s.mean() * 100),
            samples=("machine_no", "count"),
        )
        .reset_index()
        .sort_values(["avg_diff", "samples"], ascending=[False, False])
    )


def _clip_score(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return float(np.clip(value, low, high))


def _machine_number_signal(machine_no: int) -> tuple[float, str | None]:
    text = str(machine_no)
    reasons: list[str] = []
    score = 0.0
    if text[-1] in {"1", "3", "5", "6", "7", "8"}:
        score += 4
        reasons.append(f"末尾{text[-1]}")
    if len(text) >= 2 and text[-1] == text[-2]:
        score += 6
        reasons.append("ゾロ目")
    return score, "・".join(reasons) if reasons else None


def calculate_target_ranking(df: pd.DataFrame, recent_days: int = 14, limit: int = 20) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=["順位", "台番号", "機種名", "勝率", "期待差枚", "高設定期待度", "信頼度", "根拠"])

    latest_date = df["date"].max().date()
    recent_start = latest_date - timedelta(days=max(recent_days, 1) - 1)
    model_avg = df.groupby("machine_name")["diff_coins"].mean().to_dict()
    results: list[dict[str, Any]] = []

    for machine_no, group in df.groupby("machine_no"):
        group = group.sort_values("date")
        sample_count = len(group)
        avg_diff = float(group["diff_coins"].mean())
        median_diff = float(group["diff_coins"].median())
        win_rate = float(group["win"].mean() * 100)
        avg_games = float(group["games"].mean())
        recent = group[group["date"].dt.date >= recent_start]
        recent_avg = float(recent["diff_coins"].mean()) if not recent.empty else avg_diff
        recent_win = float(recent["win"].mean() * 100) if not recent.empty else win_rate
        special = group[group["special_day"]]
        special_avg = float(special["diff_coins"].mean()) if not special.empty else 0
        last_diff = int(group.iloc[-1]["diff_coins"])
        prev_diff = int(group.iloc[-2]["diff_coins"]) if sample_count >= 2 else 0
        machine_name = str(group.iloc[-1]["machine_name"])

        score = 45.0
        score += np.tanh(avg_diff / 1000) * 14
        score += np.tanh(recent_avg / 1200) * 16
        score += (win_rate - 50) * 0.25
        score += np.tanh((avg_games - 2500) / 2500) * 8
        score += np.tanh(special_avg / 1200) * 7
        score += np.tanh(model_avg.get(machine_name, 0) / 1000) * 6

        reasons: list[str] = []
        if avg_diff > 0:
            reasons.append(f"平均差枚+{avg_diff:.0f}")
        if recent_avg > avg_diff and recent_avg > 0:
            reasons.append("直近上向き")
        if special_avg > 0:
            reasons.append("特定日良好")
        if avg_games >= 3000:
            reasons.append("平均G数高め")
        if last_diff < 0 <= avg_diff:
            score += 5
            reasons.append("前日凹みからの上げ狙い")
        if prev_diff < 0 and last_diff < 0 and avg_diff > 0:
            score += 4
            reasons.append("前々日まで凹み")
        if median_diff > 0:
            score += 3
            reasons.append("中央値プラス")
        number_score, number_reason = _machine_number_signal(int(machine_no))
        score += number_score
        if number_reason:
            reasons.append(number_reason)

        reliability = _clip_score(35 + min(sample_count, 30) * 1.5 + np.tanh(avg_games / 3500) * 20)
        expectation = avg_diff * 0.45 + recent_avg * 0.35 + model_avg.get(machine_name, 0) * 0.2
        high_setting_score = _clip_score(score)

        results.append(
            {
                "台番号": int(machine_no),
                "機種名": machine_name,
                "勝率": win_rate,
                "期待差枚": expectation,
                "高設定期待度": high_setting_score,
                "信頼度": reliability,
                "根拠": " / ".join(reasons[:5]) if reasons else "サンプル不足のため弱い根拠",
                "_recent_win": recent_win,
                "_samples": sample_count,
            }
        )

    ranking = pd.DataFrame(results).sort_values(
        ["高設定期待度", "信頼度", "期待差枚"], ascending=[False, False, False]
    )
    ranking.insert(0, "順位", range(1, len(ranking) + 1))
    ranking = ranking.head(limit).copy()
    for col in ["勝率", "期待差枚", "高設定期待度", "信頼度"]:
        ranking[col] = ranking[col].round(1)
    return ranking[["順位", "台番号", "機種名", "勝率", "期待差枚", "高設定期待度", "信頼度", "根拠"]]


def machine_detail(df: pd.DataFrame, machine_no: int) -> dict[str, Any]:
    group = df[df["machine_no"] == int(machine_no)].sort_values("date")
    if group.empty:
        return {"data": group}
    group = group.copy()
    group["prev_diff"] = group["diff_coins"].shift(1)
    group["prev2_diff"] = group["diff_coins"].shift(2)
    group["expectation_trend"] = (
        group["diff_coins"].rolling(7, min_periods=1).mean().rank(pct=True).fillna(0) * 100
    )
    stats = {
        "data": group,
        "win_rate": group["win"].mean() * 100,
        "avg_diff": group["diff_coins"].mean(),
        "median_diff": group["diff_coins"].median(),
        "max_diff": group["diff_coins"].max(),
        "min_diff": group["diff_coins"].min(),
        "last_7": group.tail(7),
        "last_14": group.tail(14),
        "last_30": group.tail(30),
        "special": group[group["special_day"]],
        "weekday": weekday_trends(group),
        "prev_corr": group[["diff_coins", "prev_diff"]].corr().iloc[0, 1] if len(group) > 2 else np.nan,
        "prev2_corr": group[["diff_coins", "prev2_diff"]].corr().iloc[0, 1] if len(group) > 3 else np.nan,
    }
    return stats


def model_detail(df: pd.DataFrame, machine_name: str) -> dict[str, Any]:
    group = df[df["machine_name"] == machine_name].sort_values(["date", "machine_no"])
    if group.empty:
        return {"data": group}
    by_machine = (
        group.groupby("machine_no")
        .agg(avg_diff=("diff_coins", "mean"), win_rate=("win", lambda s: s.mean() * 100), samples=("date", "count"))
        .reset_index()
        .sort_values("avg_diff", ascending=False)
    )
    return {
        "data": group,
        "machines": int(group["machine_no"].nunique()),
        "avg_games": float(group["games"].mean()),
        "avg_diff": float(group["diff_coins"].mean()),
        "win_rate": float(group["win"].mean() * 100),
        "by_machine": by_machine,
        "daily": daily_trends(group),
        "special": special_day_trends(group),
        "strong_machines": by_machine.head(10),
        "weak_machines": by_machine.tail(10).sort_values("avg_diff"),
    }
