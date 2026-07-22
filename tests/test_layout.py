import pandas as pd

from components import layout


def test_style_diff_columns_formats_win_rate_as_percent():
    df = pd.DataFrame({"win_rate": [60.0], "avg_diff": [123.4]})

    html = layout.style_diff_columns(df, ["avg_diff"]).to_html()

    assert "勝率" in html
    assert "60%" in html
    assert "平均差枚" in html


def test_table_column_config_localizes_key_columns():
    df = pd.DataFrame(columns=["win_rate", "machine_name", "根拠"])

    config = layout.table_column_config(df)

    assert "勝率" in config
    assert "機種名" in config
    assert "根拠" in config
