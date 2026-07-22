"""Rule-based analysis for machine targeting.

This module deliberately avoids Streamlit imports so it can be tested and later
replaced with a model-based scorer.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

import numpy as np
import pandas as pd

from config import ANNIVERSARY_MONTH_DAY, DEFAULT_SPECIAL_DAY_SUFFIXES, STORE_NAME, WEEKDAY_JP


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


def _round_display_columns(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    out = df.copy()
    for col in columns:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce").fillna(0).round(0).astype(int)
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
    grouped = _round_display_columns(grouped, ["avg_diff", "win_rate", "avg_games"])
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
    out = _round_display_columns(out, ["avg_diff", "win_rate", "avg_games"])
    return out.sort_values("weekday")


def special_day_trends(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=["special_day", "avg_diff", "win_rate", "avg_games", "samples"])
    out = (
        df.groupby("special_day")
        .agg(
            avg_diff=("diff_coins", "mean"),
            win_rate=("win", lambda s: s.mean() * 100),
            avg_games=("games", "mean"),
            samples=("machine_no", "count"),
        )
        .reset_index()
    )
    return _round_display_columns(out, ["avg_diff", "win_rate", "avg_games"])


def machine_name_trends(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=["machine_name", "machines", "avg_games", "avg_diff", "win_rate", "samples"])
    out = (
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
    return _round_display_columns(out, ["avg_games", "avg_diff", "win_rate"])


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


def _default_special_day(target_date: date) -> bool:
    if (target_date.month, target_date.day) == ANNIVERSARY_MONTH_DAY:
        return True
    return str(target_date.day)[-1] in DEFAULT_SPECIAL_DAY_SUFFIXES


def _calendar_row_for_date(calendar_df: pd.DataFrame | None, target_date: date) -> dict[str, Any]:
    if calendar_df is None or calendar_df.empty:
        return {}
    cal = calendar_df.copy()
    cal["date"] = pd.to_datetime(cal["date"], errors="coerce").dt.date
    rows = cal[cal["date"] == target_date]
    if rows.empty:
        return {}
    return rows.iloc[-1].to_dict()


def target_day_context(target_date: date, calendar_df: pd.DataFrame | None = None, hint_text: str = "") -> dict[str, Any]:
    calendar_row = _calendar_row_for_date(calendar_df, target_date)
    calendar_special = calendar_row.get("special_day")
    special_day = bool(calendar_special) if calendar_special is not None and not pd.isna(calendar_special) else _default_special_day(target_date)
    event_name = str(calendar_row.get("event_name") or "").strip()
    memo = str(calendar_row.get("memo") or "").strip()
    combined_hint = "\n".join(part for part in [event_name, memo, hint_text.strip()] if part)
    return {
        "date": target_date,
        "weekday": WEEKDAY_JP[target_date.weekday()],
        "special_day": special_day,
        "event_name": event_name,
        "memo": memo,
        "hint_text": combined_hint,
    }


def _normalize_hint(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text or "").lower()
    return re.sub(r"\s+", "", normalized)


def _hint_score(machine_no: int, machine_name: str, hint_text: str) -> tuple[float, list[str]]:
    if not hint_text.strip():
        return 0.0, []

    normalized_hint = _normalize_hint(hint_text)
    normalized_machine_name = _normalize_hint(machine_name)
    score = 0.0
    reasons: list[str] = []

    if normalized_machine_name and len(normalized_machine_name) >= 2 and normalized_machine_name in normalized_hint:
        score += 18
        reasons.append("X示唆:機種名")

    explicit_numbers = {
        int(match)
        for match in re.findall(r"(?<!\d)(\d{3,4})(?:番台|番|台)", normalized_hint)
    }
    explicit_numbers.update(
        int(match)
        for match in re.findall(r"(?:台番号|台番)(\d{3,4})", normalized_hint)
    )
    if int(machine_no) in explicit_numbers:
        score += 28
        reasons.append("X示唆:台番号")

    endings = set(re.findall(r"末尾([0-9])", normalized_hint))
    if str(machine_no)[-1] in endings:
        score += 12
        reasons.append(f"X示唆:末尾{str(machine_no)[-1]}")

    if "ゾロ目" in normalized_hint and len(str(machine_no)) >= 2 and str(machine_no)[-1] == str(machine_no)[-2]:
        score += 10
        reasons.append("X示唆:ゾロ目")

    if ("角" in normalized_hint or "カド" in normalized_hint) and str(machine_no)[-1] in {"0", "1"}:
        score += 4
        reasons.append("X示唆:角候補")

    return score, reasons


def calculate_target_ranking(
    df: pd.DataFrame,
    recent_days: int = 14,
    limit: int = 20,
    target_date: date | None = None,
    calendar_df: pd.DataFrame | None = None,
    hint_text: str = "",
) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=["順位", "台番号", "機種名", "勝率", "期待差枚", "高設定期待度", "信頼度", "根拠"])

    context = target_day_context(target_date, calendar_df, hint_text) if target_date else {}
    scoring_df = df[df["date"].dt.date < target_date].copy() if target_date else df.copy()
    if scoring_df.empty:
        scoring_df = df.copy()

    reference_date = target_date or scoring_df["date"].max().date()
    recent_start = reference_date - timedelta(days=max(recent_days, 1) - 1)
    model_avg = scoring_df.groupby("machine_name")["diff_coins"].mean().to_dict()
    results: list[dict[str, Any]] = []

    for machine_no, group in scoring_df.groupby("machine_no"):
        group = group.sort_values("date")
        sample_count = len(group)
        avg_diff = float(group["diff_coins"].mean())
        median_diff = float(group["diff_coins"].median())
        win_rate = float(group["win"].mean() * 100)
        avg_games = float(group["games"].mean())
        recent = group[group["date"].dt.date >= recent_start]
        recent_avg = float(recent["diff_coins"].mean()) if not recent.empty else avg_diff
        recent_win = float(recent["win"].mean() * 100) if not recent.empty else win_rate
        same_weekday = group[group["weekday"] == context.get("weekday")] if context else group.iloc[0:0]
        weekday_avg = float(same_weekday["diff_coins"].mean()) if not same_weekday.empty else 0
        weekday_win = float(same_weekday["win"].mean() * 100) if not same_weekday.empty else win_rate

        special = group[group["special_day"]]
        normal = group[~group["special_day"]]
        special_avg = float(special["diff_coins"].mean()) if not special.empty else 0
        normal_avg = float(normal["diff_coins"].mean()) if not normal.empty else avg_diff

        exact_prev = group[group["date"].dt.date == reference_date - timedelta(days=1)]
        exact_prev2 = group[group["date"].dt.date == reference_date - timedelta(days=2)]
        last_before = group[group["date"].dt.date < reference_date].tail(1)
        prev_before = group[group["date"].dt.date < reference_date].tail(2).head(1)
        fallback_last = group.tail(1)
        fallback_prev = group.tail(2).head(1)
        last_diff = int(exact_prev.iloc[-1]["diff_coins"]) if not exact_prev.empty else int((last_before if not last_before.empty else fallback_last).iloc[-1]["diff_coins"])
        prev_diff = int(exact_prev2.iloc[-1]["diff_coins"]) if not exact_prev2.empty else (int((prev_before if not prev_before.empty else fallback_prev).iloc[-1]["diff_coins"]) if sample_count >= 2 else 0)
        machine_name = str(group.iloc[-1]["machine_name"])
        target_special_avg = special_avg if context.get("special_day") else normal_avg
        hint_score, hint_reasons = _hint_score(int(machine_no), machine_name, str(context.get("hint_text", "")))

        score = 45.0
        score += np.tanh(avg_diff / 1000) * 10
        score += np.tanh(recent_avg / 1200) * 14
        score += (win_rate - 50) * 0.25
        score += np.tanh((avg_games - 2500) / 2500) * 8
        score += np.tanh(weekday_avg / 1000) * (10 if context else 0)
        score += np.tanh(target_special_avg / 1200) * (10 if context else 7)
        score += np.tanh(model_avg.get(machine_name, 0) / 1000) * 6
        score += hint_score

        reasons: list[str] = []
        if context:
            reasons.append(f"対象日{context['weekday']}曜")
            if context.get("special_day"):
                reasons.append("対象日は特定日")
        reasons.extend(hint_reasons)
        if avg_diff > 0:
            reasons.append(f"平均差枚+{avg_diff:.0f}")
        if recent_avg > avg_diff and recent_avg > 0:
            reasons.append("直近上向き")
        if context and not same_weekday.empty and weekday_avg > 0:
            reasons.append(f"{context['weekday']}曜良好")
        if context.get("special_day") and special_avg > 0:
            reasons.append("特定日良好")
        if avg_games >= 3000:
            reasons.append("平均G数高め")
        if last_diff < 0 <= avg_diff:
            score += 5
            reasons.append("前日/直近凹みからの上げ狙い")
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

        reliability = _clip_score(35 + min(sample_count, 30) * 1.3 + np.tanh(avg_games / 3500) * 18 + min(len(same_weekday), 8) * 1.2)
        expectation = (
            avg_diff * 0.25
            + recent_avg * 0.28
            + weekday_avg * (0.18 if context else 0)
            + target_special_avg * (0.14 if context else 0.22)
            + model_avg.get(machine_name, 0) * 0.15
            + hint_score * 18
        )
        high_setting_score = _clip_score(score)

        row = {
            "台番号": int(machine_no),
            "機種名": machine_name,
            "勝率": weekday_win if context and not same_weekday.empty else win_rate,
            "期待差枚": expectation,
            "高設定期待度": high_setting_score,
            "信頼度": reliability,
            "根拠": " / ".join(reasons[:6]) if reasons else "サンプル不足のため弱い根拠",
            "_recent_win": recent_win,
            "_samples": sample_count,
        }
        if context:
            row["対象日"] = context["date"].isoformat()
            row["対象曜日"] = context["weekday"]
            row["特定日"] = "特定日" if context["special_day"] else "通常日"
        results.append(row)

    ranking = pd.DataFrame(results).sort_values(
        ["高設定期待度", "信頼度", "期待差枚"], ascending=[False, False, False]
    )
    ranking.insert(0, "順位", range(1, len(ranking) + 1))
    ranking = ranking.head(limit).copy()
    for col in ["勝率", "期待差枚", "高設定期待度", "信頼度"]:
        ranking[col] = ranking[col].round(0).astype(int)
    columns = ["順位"]
    if target_date:
        columns.extend(["対象日", "対象曜日", "特定日"])
    columns.extend(["台番号", "機種名", "勝率", "期待差枚", "高設定期待度", "信頼度", "根拠"])
    return ranking[columns]


def machine_detail(df: pd.DataFrame, machine_no: int) -> dict[str, Any]:
    group = df[df["machine_no"] == int(machine_no)].sort_values("date")
    if group.empty:
        return {"data": group}
    group = group.copy()
    group["prev_diff"] = group["diff_coins"].shift(1)
    group["prev2_diff"] = group["diff_coins"].shift(2)
    group["expectation_trend"] = (
        group["diff_coins"].rolling(7, min_periods=1).mean().rank(pct=True).fillna(0) * 100
    ).round(0)
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
    by_machine = _round_display_columns(by_machine, ["avg_diff", "win_rate"])
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
