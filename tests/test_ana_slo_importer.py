from __future__ import annotations

import pytest

from ana_slo_importer import (
    ParseError,
    TargetStoreError,
    UrlValidationError,
    _is_missing_playwright_browser_error,
    import_from_uploaded_html,
    is_target_store_url,
    parse_ana_slo_html,
    parse_date_from_text,
    parse_int,
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
        import_from_uploaded_html(html, VALID_URL)


def test_missing_table_raises_parse_error():
    html = f"<html><body><h1>2026/07/07 {STORE_NAME}</h1><p>no table</p></body></html>"
    with pytest.raises(ParseError):
        parse_ana_slo_html(html, VALID_URL)
