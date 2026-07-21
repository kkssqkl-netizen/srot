from __future__ import annotations

import pandas as pd

import analyzer


def _sample_df() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"store_name": "マルハン綾瀬上土棚店", "date": "2026-07-01", "machine_no": 101, "machine_name": "A", "games": 5000, "diff_coins": 2000, "bb": 1, "rb": 1, "at_hits": 0, "first_hits": 0, "special_day": True},
            {"store_name": "マルハン綾瀬上土棚店", "date": "2026-07-02", "machine_no": 101, "machine_name": "A", "games": 4200, "diff_coins": -500, "bb": 1, "rb": 1, "at_hits": 0, "first_hits": 0, "special_day": False},
            {"store_name": "マルハン綾瀬上土棚店", "date": "2026-07-03", "machine_no": 101, "machine_name": "A", "games": 5200, "diff_coins": 3500, "bb": 1, "rb": 1, "at_hits": 0, "first_hits": 0, "special_day": True},
            {"store_name": "マルハン綾瀬上土棚店", "date": "2026-07-01", "machine_no": 102, "machine_name": "A", "games": 900, "diff_coins": -1200, "bb": 1, "rb": 1, "at_hits": 0, "first_hits": 0, "special_day": True},
            {"store_name": "マルハン綾瀬上土棚店", "date": "2026-07-02", "machine_no": 103, "machine_name": "B", "games": 3200, "diff_coins": 100, "bb": 1, "rb": 1, "at_hits": 0, "first_hits": 0, "special_day": False},
        ]
    )


def test_store_summary_and_trends():
    df = analyzer.prepare_dataframe(_sample_df())
    summary = analyzer.store_summary(df)
    assert summary["records"] == 5
    assert summary["days"] == 3
    assert summary["machines"] == 3
    assert summary["win_rate"] == 60.0
    daily = analyzer.daily_trends(df)
    assert set(["date", "total_diff", "avg_diff", "win_rate"]).issubset(daily.columns)


def test_filters_min_games_weekday_and_special():
    df = analyzer.prepare_dataframe(_sample_df())
    filters = analyzer.AnalysisFilters(min_games=3000, weekdays=["金"], special_only=True)
    filtered = analyzer.apply_filters(df, filters)
    assert len(filtered) == 1
    assert int(filtered.iloc[0]["machine_no"]) == 101


def test_score_calculation_returns_required_columns():
    df = analyzer.prepare_dataframe(_sample_df())
    ranking = analyzer.calculate_target_ranking(df, recent_days=7, limit=5)
    assert list(ranking.columns) == ["順位", "台番号", "機種名", "勝率", "期待差枚", "高設定期待度", "信頼度", "根拠"]
    assert int(ranking.iloc[0]["台番号"]) == 101
    assert 0 <= ranking.iloc[0]["高設定期待度"] <= 100

