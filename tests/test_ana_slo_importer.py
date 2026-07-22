from __future__ import annotations

from datetime import date

import pytest

from ana_slo_importer import (
    BlankFetchError,
    FetchResult,
    NoMachineDataError,
    ParseError,
    TargetStoreError,
    UrlValidationError,
    _is_missing_playwright_browser_error,
    contains_target_store,
    import_from_page_text,
    import_from_uploaded_html,
    is_target_store_url,
    parse_ana_slo_html,
    parse_date_from_text,
    parse_int,
    import_from_url,
    validate_daily_url,
)
from config import STORE_NAME


VALID_URL = "https://ana-slo.com/2026-07-07-%E3%83%9E%E3%83%AB%E3%83%8F%E3%83%B3%E7%B6%BE%E7%80%AC%E4%B8%8A%E5%9C%9F%E6%A3%9A%E5%BA%97-data/"

SAMPLE_HTML = f"""
<html>
  <head><title>2026/07/07 {STORE_NAME} データまとめ</title></head>
  <body>
    <h1>2026/07/07 {STORE_NAME} データまとめ</h1>
    <h4>マイジャグラーV</h4>
    <table>
      <tr><th>台番号</th><th>G数</th><th>差枚</th><th>BB</th><th>RB</th><th>合成確率</th></tr>
      <tr><td>601</td><td>7,555</td><td>-400</td><td>23</td><td>30</td><td>1/142.5</td></tr>
      <tr><td>602</td><td>7,256</td><td>+300</td><td>27</td><td>17</td><td>1/164.9</td></tr>
    </table>
    <h4>末尾ゾロ目</h4>
    <table>
      <tr><th>機種名</th><th>台番号</th><th>G数</th><th>差枚</th><th>BB</th><th>RB</th><th>ART</th></tr>
      <tr><td>化物語</td><td>500</td><td>4,685</td><td>+3,000</td><td>65</td><td>26</td><td>0</td></tr>
    </table>
  </body>
</html>
"""


def test_parse_int_handles_signs_and_separators():
    assert parse_int("+3,000枚") == 3000
    assert parse_int("−400") == -400
    assert parse_int("–") == 0


def test_missing_playwright_browser_error_is_detected():
    message = "BrowserType.launch: Executable doesn't exist. Please run playwright install"
    assert _is_missing_playwright_browser_error(message)


def test_parse_date_extracts_from_url_or_text():
    assert parse_date_from_text(VALID_URL).isoformat() == "2026-07-07"
    assert parse_date_from_text("投稿日：2026年7月7日").isoformat() == "2026-07-07"


def test_target_store_daily_url_validation():
    assert validate_daily_url(VALID_URL).isoformat() == "2026-07-07"
    assert is_target_store_url(VALID_URL)


def test_target_store_detection_allows_minor_spacing_variations():
    assert contains_target_store("マルハン 綾瀬 上土棚 データまとめ")


@pytest.mark.parametrize(
    "url,exc",
    [
        ("https://example.com/2026-07-07-%E3%83%9E%E3%83%AB%E3%83%8F%E3%83%B3%E7%B6%BE%E7%80%AC%E4%B8%8A%E5%9C%9F%E6%A3%9A%E5%BA%97-data/", UrlValidationError),
        ("https://ana-slo.com/2026-07-07-%E4%BB%96%E5%BA%97-data/", TargetStoreError),
        ("https://ana-slo.com/%E3%83%9B%E3%83%BC%E3%83%AB%E3%83%87%E3%83%BC%E3%82%BF/%E7%A5%9E%E5%A5%88%E5%B7%9D%E7%9C%8C/%E3%83%9E%E3%83%AB%E3%83%8F%E3%83%B3%E7%B6%BE%E7%80%AC%E4%B8%8A%E5%9C%9F%E6%A3%9A%E5%BA%97-%E3%83%87%E3%83%BC%E3%82%BF%E4%B8%80%E8%A6%A7/", UrlValidationError),
    ],
)
def test_invalid_urls_are_rejected(url, exc):
    with pytest.raises(exc):
        validate_daily_url(url)


def test_parse_ana_slo_html_extracts_all_machine_rows():
    result = parse_ana_slo_html(SAMPLE_HTML, VALID_URL)
    assert result.target_date.isoformat() == "2026-07-07"
    assert len(result.records) == 3
    record_601 = next(row for row in result.records if row["machine_no"] == 601)
    assert record_601["machine_name"] == "マイジャグラーV"
    assert record_601["games"] == 7555
    assert record_601["diff_coins"] == -400
    record_500 = next(row for row in result.records if row["machine_no"] == 500)
    assert record_500["machine_name"] == "化物語"
    assert record_500["diff_coins"] == 3000


def test_valid_daily_url_allows_html_without_store_name_in_body():
    html = """
    <html><body>
      <h4>マイジャグラーV</h4>
      <table>
        <tr><th>台番号</th><th>G数</th><th>差枚</th></tr>
        <tr><td>601</td><td>7,555</td><td>+300</td></tr>
      </table>
    </body></html>
    """
    result = parse_ana_slo_html(html, VALID_URL)
    assert len(result.records) == 1
    assert result.records[0]["machine_no"] == 601


def test_parse_markdownish_table_extracts_machine_rows():
    html = f"""
    <html><body><pre>
    # 2026/07/07 {STORE_NAME} データまとめ
    #### スーパーリオエース2
    台番号 | G数 | 差枚 | BB | RB
    --- | --- | --- | --- | ---
    509 | 3,255 | -100 | 28 | 19
    510 | 5,478 | +700 | 48 | 24

    #### 1台設置機種
    機種名 | 台番号 | G数 | 差枚 | BB | RB
    --- | --- | --- | --- | --- | ---
    アクダマドライブ | 490 | 2,967 | +700 | 15 | 9
    </pre></body></html>
    """
    result = parse_ana_slo_html(html, VALID_URL)
    assert len(result.records) == 3
    record_509 = next(row for row in result.records if row["machine_no"] == 509)
    assert record_509["machine_name"] == "スーパーリオエース2"
    record_490 = next(row for row in result.records if row["machine_no"] == 490)
    assert record_490["machine_name"] == "アクダマドライブ"


def test_parse_line_block_table_extracts_machine_rows():
    html = f"""
    <html><body>
      <h1>2026/07/07 {STORE_NAME} データまとめ</h1>
      <section>
        <h4>沖ドキ!GOLD</h4>
        <div>データ表示</div><div>グラフ表示</div>
        <div>台番号</div><div>G数</div><div>差枚</div><div>BB</div><div>RB</div><div>合成確率</div>
        <div>725</div><div>4,796</div><div>+2,300</div><div>39</div><div>17</div><div>1/85.6</div>
        <div>726</div><div>3,323</div><div>+1,300</div><div>27</div><div>8</div><div>1/94.9</div>
        <div>平均</div><div>4,046</div><div>+288</div><div>26</div><div>12</div><div>1/105.8</div>
      </section>
      <section>
        <h4>末尾7</h4>
        <div>機種名</div><div>台番号</div><div>G数</div><div>差枚</div><div>BB</div><div>RB</div><div>ART</div>
        <div>スマスロ北斗の拳</div><div>547</div><div>5,886</div><div>+4,100</div><div>93</div><div>17</div><div>0</div>
      </section>
    </body></html>
    """
    result = parse_ana_slo_html(html, VALID_URL)
    assert len(result.records) == 3
    record_725 = next(row for row in result.records if row["machine_no"] == 725)
    assert record_725["machine_name"] == "沖ドキ!GOLD"
    assert record_725["diff_coins"] == 2300
    record_547 = next(row for row in result.records if row["machine_no"] == 547)
    assert record_547["machine_name"] == "スマスロ北斗の拳"


def test_blank_fetch_html_is_reported_as_fetch_error():
    blank_html = '<html><head><meta name="color-scheme" content="light dark"></head><body><pre> </pre></body></html>'
    with pytest.raises(BlankFetchError):
        parse_ana_slo_html(blank_html, VALID_URL)


def test_import_from_page_text_extracts_tab_delimited_rows():
    text = f"""
    2026/07/07 {STORE_NAME} データまとめ
    沖ドキ!GOLD
    データ表示
    グラフ表示
    台番号\tG数\t差枚\tBB\tRB\t合成確率
    725\t4,796\t+2,300\t39\t17\t1/85.6
    726\t3,323\t+1,300\t27\t8\t1/94.9
    平均\t4,046\t+288\t26\t12\t1/105.8

    末尾5
    機種名\t台番号\tG数\t差枚\tBB\tRB\tART
    かぐや様は告らせたい\t485\t6,057\t+5,300\t45\t8\t0
    """
    result = import_from_page_text(text, VALID_URL)
    assert len(result.records) == 3
    record_725 = next(row for row in result.records if row["machine_no"] == 725)
    assert record_725["machine_name"] == "沖ドキ!GOLD"
    record_485 = next(row for row in result.records if row["machine_no"] == 485)
    assert record_485["machine_name"] == "かぐや様は告らせたい"
    assert result.fetch_method == "pasted_text"


def test_import_from_url_retries_playwright_when_static_html_has_no_table(monkeypatch):
    calls = []

    def fake_fetch_daily_page(source_url):
        calls.append("requests")
        return FetchResult(
            html=f"<html><body><h1>{STORE_NAME}</h1><p>loading</p></body></html>",
            method="requests",
            status_code=200,
        )

    def fake_fetch_html_with_playwright(source_url):
        calls.append("playwright")
        return FetchResult(html=SAMPLE_HTML, method="playwright")

    monkeypatch.setattr("ana_slo_importer.fetch_daily_page", fake_fetch_daily_page)
    monkeypatch.setattr("ana_slo_importer.fetch_html_with_playwright", fake_fetch_html_with_playwright)
    result = import_from_url(VALID_URL)
    assert calls == ["requests", "playwright"]
    assert len(result.records) == 3
    assert result.fetch_method == "playwright"


def test_upload_html_requires_target_store_text():
    html = """
    <html><body>
      <h1>2026/07/07 他店 データまとめ</h1>
      <p>このHTMLは対象店舗名を含まないため拒否されるべきです。</p>
      <table>
        <tr><th>台番号</th><th>G数</th><th>差枚</th></tr>
        <tr><td>1</td><td>1000</td><td>100</td></tr>
      </table>
    </body></html>
    """
    with pytest.raises(TargetStoreError):
        import_from_uploaded_html(html, "uploaded:test.html", expected_date=date(2026, 7, 7))


def test_missing_table_raises_parse_error():
    html = f"""
    <html><body>
      <h1>2026/07/07 {STORE_NAME}</h1>
      <p>このページには店舗サマリーだけがあり、台番号別の詳細データはまだありません。</p>
      <p>総差枚、平均G数、勝率などの概要欄のみが表示されています。</p>
    </body></html>
    """
    with pytest.raises(NoMachineDataError):
        parse_ana_slo_html(html, VALID_URL)
