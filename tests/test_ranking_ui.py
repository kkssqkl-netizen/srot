import pandas as pd

from app_pages import ranking


def test_rank_card_html_has_no_indented_code_block_lines():
    row = {
        "順位": 2,
        "台番号": 661,
        "機種名": "東京喰種",
        "高設定期待度": 100,
        "期待差枚": 1479,
        "勝率": 100,
        "信頼度": 66,
        "同機種順位": "1/3位",
        "サンプル数": 8,
        "日別要因": "対象日末尾1 / 末尾1日+850",
        "不安材料": "大きな不安材料なし",
        "根拠": "平均差枚+1680 / 水曜良好 / 前日/直近凹みからの上げ狙い",
    }

    html = ranking._rank_card_html(row)

    assert "\n    <div" not in html
    assert 'class="rank-card rank-2"' in html
    assert "同機種 1/3位" in html
    assert "日別要因:" in html
    assert "不安:" in html
    assert "100%" in html


def test_ranking_list_html_wraps_reason_text():
    df = pd.DataFrame(
        [
            {
                "順位": 4,
                "台番号": 508,
                "機種名": "バイオハザード RE:3",
                "高設定期待度": 99,
                "期待差枚": 2098,
                "勝率": 100,
                "信頼度": 74,
                "同機種順位": "2/4位",
                "サンプル数": 12,
                "日別要因": "対象日末尾8 / 8日傾向+1200",
                "不安材料": "前日出過ぎ / 直近勝率低め",
                "根拠": "平均差枚+1527 / 直近上向き / 水曜良好 / 平均G数高め / 中央値プラス / 末尾8",
            }
        ]
    )

    html = ranking._ranking_list_html(df)

    assert "\n    <div" not in html
    assert 'class="rank-list-day"' in html
    assert 'class="rank-list-reason"' in html
    assert 'class="rank-list-risk"' in html
    assert "対象日末尾8" in html
    assert "平均差枚+1527" in html
    assert "前日出過ぎ" in html
    assert "100%" in html
