"""ana-slo daily page fetcher and parser.

The parser is intentionally table-driven and tolerant of header variations so
that changes in ana-slo markup can be fixed in one place.
"""

from __future__ import annotations

import re
import time
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from typing import Iterable
from urllib.parse import unquote, urlparse

import requests
from bs4 import BeautifulSoup

from config import (
    ANA_SLO_DOMAIN,
    ANNIVERSARY_MONTH_DAY,
    DEFAULT_SPECIAL_DAY_SUFFIXES,
    STORE_NAME,
)


class AnaSloError(Exception):
    user_message = "ana-sloデータの取得または解析に失敗しました。"


class UrlValidationError(AnaSloError):
    user_message = "URL形式が正しくありません。ana-sloの日別ページURLを入力してください。"


class TargetStoreError(AnaSloError):
    user_message = "対象店舗以外のURLは登録できません。"


class FetchError(AnaSloError):
    user_message = "ページ取得に失敗しました。時間をおいて再試行するか、保存HTMLをアップロードしてください。"


class ParseError(AnaSloError):
    user_message = "ページ内の表を解析できませんでした。HTML構造が変わっている可能性があります。"


@dataclass(frozen=True)
class FetchResult:
    html: str
    method: str
    status_code: int | None = None


@dataclass(frozen=True)
class ImportResult:
    store_name: str
    target_date: date
    source_url: str
    fetched_at: datetime
    records: list[dict]
    fetch_method: str = "uploaded_html"


@dataclass(frozen=True)
class MachineRecord:
    store_name: str
    date: date
    machine_no: int
    machine_name: str
    games: int
    diff_coins: int
    bb: int
    rb: int
    at_hits: int
    first_hits: int
    special_day: bool
    source_url: str
    fetched_at: datetime

    def to_payload(self) -> dict:
        payload = asdict(self)
        payload["date"] = self.date.isoformat()
        payload["fetched_at"] = self.fetched_at.isoformat()
        return payload


def normalize_text(text: str | None) -> str:
    if text is None:
        return ""
    return re.sub(r"\s+", " ", str(text).replace("\xa0", " ")).strip()


def parse_int(value: object, default: int = 0) -> int:
    text = normalize_text(str(value) if value is not None else "")
    if not text or text in {"-", "–", "—", "ー"}:
        return default
    text = text.replace("−", "-").replace("▲", "-").replace(",", "")
    text = text.replace("枚", "").replace("G", "").replace("回", "")
    match = re.search(r"[+-]?\d+", text)
    if not match:
        return default
    return int(match.group(0))


def parse_rate_count(value: object) -> tuple[float | None, int | None, int | None]:
    text = normalize_text(str(value) if value is not None else "")
    match = re.search(r"([0-9.]+)%\((\d+)/(\d+)\)", text)
    if not match:
        return None, None, None
    return float(match.group(1)), int(match.group(2)), int(match.group(3))


def parse_date_from_text(text: str) -> date | None:
    decoded = unquote(text)
    patterns = [
        r"(?P<y>20\d{2})[-/年](?P<m>\d{1,2})[-/月](?P<d>\d{1,2})",
        r"(?P<y>20\d{2})\s*年\s*(?P<m>\d{1,2})\s*月\s*(?P<d>\d{1,2})\s*日",
    ]
    for pattern in patterns:
        match = re.search(pattern, decoded)
        if match:
            return date(int(match.group("y")), int(match.group("m")), int(match.group("d")))
    return None


def is_default_special_day(target_date: date) -> bool:
    if (target_date.month, target_date.day) == ANNIVERSARY_MONTH_DAY:
        return True
    return str(target_date.day)[-1] in DEFAULT_SPECIAL_DAY_SUFFIXES


def validate_daily_url(source_url: str) -> date:
    if not source_url:
        raise UrlValidationError("URLが空です。")
    parsed = urlparse(source_url)
    if parsed.scheme not in {"https", "http"} or not parsed.netloc:
        raise UrlValidationError("URL形式が正しくありません。")
    host = parsed.netloc.lower()
    if host != ANA_SLO_DOMAIN and not host.endswith(f".{ANA_SLO_DOMAIN}"):
        raise UrlValidationError("ana-slo.com のURLではありません。")

    decoded_path = unquote(parsed.path)
    if STORE_NAME not in decoded_path:
        raise TargetStoreError(f"{STORE_NAME} の日別ページURLではありません。")
    target_date = parse_date_from_text(decoded_path)
    if not target_date:
        raise UrlValidationError("日付を含む日別ページURLではありません。")
    if "データ一覧" in decoded_path or "hall" in decoded_path.lower():
        raise UrlValidationError("店舗一覧ページではなく、日別ページURLを入力してください。")
    return target_date


def is_target_store_url(source_url: str) -> bool:
    try:
        validate_daily_url(source_url)
        return True
    except AnaSloError:
        return False


def fetch_html_with_requests(source_url: str, timeout: int = 20) -> FetchResult:
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; personal-analysis-tool/1.0; +manual-one-url)",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "ja,en-US;q=0.7,en;q=0.3",
    }
    try:
        response = requests.get(source_url, headers=headers, timeout=timeout)
    except requests.Timeout as exc:
        raise FetchError("タイムアウトしました。") from exc
    except requests.RequestException as exc:
        raise FetchError(str(exc)) from exc

    if response.status_code == 403:
        raise FetchError("403 Forbidden")
    if response.status_code >= 400:
        raise FetchError(f"HTTP {response.status_code}")
    response.encoding = response.apparent_encoding or response.encoding
    return FetchResult(html=response.text, method="requests", status_code=response.status_code)


def fetch_html_with_playwright(source_url: str, timeout_ms: int = 30000) -> FetchResult:
    try:
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        raise FetchError("Playwright が利用できません。保存HTMLアップロードを使ってください。") from exc

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(locale="ja-JP")
            page.goto(source_url, wait_until="domcontentloaded", timeout=timeout_ms)
            page.wait_for_timeout(1500)
            html = page.content()
            browser.close()
            return FetchResult(html=html, method="playwright", status_code=None)
    except PlaywrightTimeoutError as exc:
        raise FetchError("Playwright取得がタイムアウトしました。") from exc
    except Exception as exc:
        raise FetchError(str(exc)) from exc


def fetch_daily_page(source_url: str) -> FetchResult:
    validate_daily_url(source_url)
    try:
        return fetch_html_with_requests(source_url)
    except FetchError as first_error:
        if "403" not in str(first_error) and "Forbidden" not in str(first_error):
            raise
        time.sleep(1.0)
        return fetch_html_with_playwright(source_url)


def _cell_texts(row) -> list[str]:
    return [normalize_text(cell.get_text(" ", strip=True)) for cell in row.find_all(["th", "td"])]


def _find_col(headers: list[str], candidates: Iterable[str]) -> int | None:
    normalized_headers = [h.replace(" ", "") for h in headers]
    for candidate in candidates:
        target = candidate.replace(" ", "")
        for index, header in enumerate(normalized_headers):
            if header == target or target in header:
                return index
    return None


def _heading_for_table(table) -> str:
    heading = table.find_previous(["h2", "h3", "h4", "h5", "h6"])
    if not heading:
        return ""
    text = normalize_text(heading.get_text(" ", strip=True))
    for noise in ("データ表示", "グラフ表示"):
        text = text.replace(noise, "")
    return normalize_text(text.strip(" ・"))


def _parse_table(table, target_date: date, source_url: str, fetched_at: datetime) -> list[MachineRecord]:
    rows = table.find_all("tr")
    if len(rows) < 2:
        return []

    headers = _cell_texts(rows[0])
    machine_no_col = _find_col(headers, ["台番号", "台番"])
    games_col = _find_col(headers, ["G数", "総G数", "ゲーム数", "総ゲーム数", "総回転数", "回転数"])
    diff_col = _find_col(headers, ["差枚", "差枚数"])
    if machine_no_col is None or games_col is None or diff_col is None:
        return []

    machine_name_col = _find_col(headers, ["機種名", "機種"])
    bb_col = _find_col(headers, ["BB", "BB回数"])
    rb_col = _find_col(headers, ["RB", "RB回数"])
    at_col = _find_col(headers, ["AT", "ART", "AT回数", "ART回数"])
    first_col = _find_col(headers, ["初当たり", "初当り", "初当たり回数", "初当り回数"])

    machine_hint = _heading_for_table(table)
    records: list[MachineRecord] = []
    for row in rows[1:]:
        cells = _cell_texts(row)
        if len(cells) <= max(machine_no_col, games_col, diff_col):
            continue

        machine_no = parse_int(cells[machine_no_col], default=-1)
        if machine_no < 0:
            continue

        machine_name = machine_hint
        if machine_name_col is not None and machine_name_col < len(cells):
            machine_name = normalize_text(cells[machine_name_col])
        if not machine_name:
            machine_name = "機種名未取得"

        games = parse_int(cells[games_col])
        diff_coins = parse_int(cells[diff_col])
        bb = parse_int(cells[bb_col]) if bb_col is not None and bb_col < len(cells) else 0
        rb = parse_int(cells[rb_col]) if rb_col is not None and rb_col < len(cells) else 0
        at_hits = parse_int(cells[at_col]) if at_col is not None and at_col < len(cells) else 0
        first_hits = parse_int(cells[first_col]) if first_col is not None and first_col < len(cells) else at_hits

        records.append(
            MachineRecord(
                store_name=STORE_NAME,
                date=target_date,
                machine_no=machine_no,
                machine_name=machine_name,
                games=games,
                diff_coins=diff_coins,
                bb=bb,
                rb=rb,
                at_hits=at_hits,
                first_hits=first_hits,
                special_day=is_default_special_day(target_date),
                source_url=source_url,
                fetched_at=fetched_at,
            )
        )
    return records


def parse_ana_slo_html(html: str, source_url: str, expected_date: date | None = None) -> ImportResult:
    if not html or len(html) < 100:
        raise ParseError("HTMLが空、または短すぎます。")

    target_date = expected_date or parse_date_from_text(source_url) or parse_date_from_text(html[:5000])
    if not target_date:
        raise ParseError("日付が取得できません。")

    try:
        soup = BeautifulSoup(html, "lxml")
    except Exception:
        soup = BeautifulSoup(html, "html.parser")
    page_text = normalize_text(soup.get_text(" ", strip=True)[:5000])
    if STORE_NAME not in page_text:
        raise TargetStoreError(f"{STORE_NAME} のページではありません。")

    fetched_at = datetime.now(timezone.utc)
    unique: dict[tuple[date, int], MachineRecord] = {}
    for table in soup.find_all("table"):
        for record in _parse_table(table, target_date, source_url, fetched_at):
            unique[(record.date, record.machine_no)] = record

    records = [record.to_payload() for record in sorted(unique.values(), key=lambda item: item.machine_no)]
    if not records:
        raise ParseError("台番号・G数・差枚を含む表が見つかりません。")

    return ImportResult(
        store_name=STORE_NAME,
        target_date=target_date,
        source_url=source_url,
        fetched_at=fetched_at,
        records=records,
    )


def import_from_url(source_url: str) -> ImportResult:
    target_date = validate_daily_url(source_url)
    fetched = fetch_daily_page(source_url)
    result = parse_ana_slo_html(fetched.html, source_url=source_url, expected_date=target_date)
    return ImportResult(
        store_name=result.store_name,
        target_date=result.target_date,
        source_url=result.source_url,
        fetched_at=result.fetched_at,
        records=result.records,
        fetch_method=fetched.method,
    )


def import_from_uploaded_html(html: str, source_url: str, expected_date: date | None = None) -> ImportResult:
    if source_url and source_url.startswith("http"):
        expected_date = expected_date or validate_daily_url(source_url)
    return parse_ana_slo_html(html, source_url=source_url or "uploaded_html", expected_date=expected_date)
