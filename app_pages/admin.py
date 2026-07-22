from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
import streamlit as st

import auth
import database
from ana_slo_importer import AnaSloError, import_from_page_text_bundle, import_from_uploaded_html, import_from_url, validate_daily_url
from components import layout
from config import MIN_IMPORT_INTERVAL_SECONDS, STORE_NAME
from services import data_service


_COPY_BOOKMARKLET = (
    "javascript:(async()=>{const t=['ANA-SLO-URL: '+location.href,"
    "'ANA-SLO-TITLE: '+document.title,"
    "'ANA-SLO-COPIED-AT: '+new Date().toISOString(),'',document.body.innerText].join('\\n');"
    "try{await navigator.clipboard.writeText(t);alert('コピーしました')}"
    "catch(e){prompt('コピーしてください',t)}})()"
)


def _decode_upload(uploaded_file) -> str:
    raw = uploaded_file.read()
    for encoding in ("utf-8", "cp932", "shift_jis"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="ignore")


def _is_session_rate_limited(source_url: str) -> tuple[bool, int]:
    key = f"last_import:{source_url}"
    last = st.session_state.get(key)
    if not last:
        return False, 0
    elapsed = (datetime.now(timezone.utc) - last).total_seconds()
    remaining = int(MIN_IMPORT_INTERVAL_SECONDS - elapsed)
    return elapsed < MIN_IMPORT_INTERVAL_SECONDS, max(remaining, 0)


def _mark_session_import(source_url: str) -> None:
    st.session_state[f"last_import:{source_url}"] = datetime.now(timezone.utc)


def _records_dataframe(records: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(records)
    columns = [
        "date",
        "machine_no",
        "machine_name",
        "games",
        "diff_coins",
        "bb",
        "rb",
        "at_hits",
        "first_hits",
        "special_day",
        "source_url",
        "fetched_at",
    ]
    return df[[col for col in columns if col in df.columns]]


def _set_import_preview(results: list) -> None:
    records = [record for result in results for record in result.records]
    dates = sorted({result.target_date for result in results})
    import_entries = [
        {
            "source_url": result.source_url,
            "target_date": result.target_date,
            "records_found": len(result.records),
            "fetch_method": result.fetch_method,
        }
        for result in results
    ]
    st.session_state["import_preview"] = {
        "source_url": results[0].source_url if len(results) == 1 else f"bulk_pasted_text:{len(results)}pages",
        "target_date": results[0].target_date if len(results) == 1 else dates[0],
        "target_dates": dates,
        "records": records,
        "fetch_method": results[0].fetch_method if len(results) == 1 else "bulk_pasted_text",
        "import_entries": import_entries,
    }


def _save_preview(profile: dict) -> None:
    preview = st.session_state.get("import_preview")
    if not preview:
        st.warning("保存するプレビューがありません。")
        return
    try:
        summary = database.upsert_machine_records(preview["records"], st.session_state.get("access_token"))
        log_entries = preview.get("import_entries") or [
            {
                "source_url": preview["source_url"],
                "target_date": preview["target_date"],
                "records_found": len(preview["records"]),
            }
        ]
        for entry in log_entries:
            database.insert_import_log(
                user_id=profile.get("id"),
                source_url=entry["source_url"],
                target_date=str(entry["target_date"]),
                status="success",
                records_found=int(entry["records_found"]),
                records_added=summary["records_added"] if len(log_entries) == 1 else 0,
                error_message=None,
                access_token=st.session_state.get("access_token"),
            )
        data_service.clear_data_cache()
        st.success(
            f"登録しました。追加 {summary['records_added']}件 / 更新 {summary['records_updated']}件 / 合計 {summary['records_total']}件"
        )
        st.session_state.pop("import_preview", None)
    except Exception as exc:
        database.insert_import_log(
            user_id=profile.get("id"),
            source_url=preview.get("source_url", ""),
            target_date=str(preview.get("target_date", "")),
            status="error",
            records_found=len(preview.get("records", [])),
            records_added=0,
            error_message=str(exc),
            access_token=st.session_state.get("access_token"),
        )
        st.error("Supabaseへの保存に失敗しました。")
        st.caption(str(exc))


def _render_url_import(profile: dict) -> None:
    st.subheader("ana-slo日別URL取込")
    source_url = st.text_input("日別ページURL", placeholder="https://ana-slo.com/2026-07-07-マルハン綾瀬上土棚店-data/")
    if st.button("URLから取得", type="primary", use_container_width=True):
        target_date = None
        try:
            target_date = validate_daily_url(source_url.strip())
            limited, remaining = _is_session_rate_limited(source_url.strip())
            if limited:
                st.warning(f"同じURLの連続実行を制限しています。あと {remaining} 秒待ってください。")
                return
            with st.spinner("ページを取得して解析しています..."):
                result = import_from_url(source_url.strip())
            _mark_session_import(source_url.strip())
            _set_import_preview([result])
            st.success(f"{target_date} のデータを {len(result.records)} 件取得しました（{result.fetch_method}）。")
        except AnaSloError as exc:
            st.error(exc.user_message)
            st.caption(str(exc))
            try:
                database.insert_import_log(
                    user_id=profile.get("id"),
                    source_url=source_url.strip(),
                    target_date=str(target_date) if target_date else None,
                    status="error",
                    records_found=0,
                    records_added=0,
                    error_message=str(exc),
                    access_token=st.session_state.get("access_token"),
                )
            except Exception:
                pass
        except Exception as exc:
            st.error("予期しないエラーが発生しました。")
            st.caption(str(exc))


def _render_html_import() -> None:
    st.subheader("保存HTMLファイル取込")
    source_url = st.text_input("元ページURL（任意。ただし入力時は対象店舗の日別URLのみ可）", key="html_source_url")
    expected_date = st.date_input("日付（URLから取れない保存HTML用）", key="html_expected_date")
    uploaded = st.file_uploader("ブラウザで保存したHTMLファイル", type=["html", "htm"])
    if st.button("HTMLを解析", use_container_width=True):
        if not uploaded:
            st.warning("HTMLファイルを選択してください。")
            return
        try:
            html = _decode_upload(uploaded)
            with st.spinner("HTMLを解析しています..."):
                result = import_from_uploaded_html(
                    html,
                    source_url=source_url.strip() or f"uploaded:{uploaded.name}",
                    expected_date=None if source_url.strip() else expected_date,
                )
            _set_import_preview([result])
            st.success(f"{result.target_date} のデータを {len(result.records)} 件解析しました。")
        except AnaSloError as exc:
            st.error(exc.user_message)
            st.caption(str(exc))
        except Exception as exc:
            st.error("HTML解析に失敗しました。")
            st.caption(str(exc))


def _render_text_import() -> None:
    st.subheader("コピー本文取込")
    with st.expander("コピー支援ブックマークレット"):
        st.code(_COPY_BOOKMARKLET, language="javascript")
        st.caption("ブックマークとして保存し、ana-slo日別ページ上で押すとURLと本文をまとめてコピーできます。")
    source_url = st.text_input("元ページURL（単一ページ本文用）", key="text_source_url")
    expected_date = st.date_input("日付（URLがない単一ページ本文用）", key="text_expected_date")
    page_text = st.text_area("コピーしたページ本文（複数日まとめ貼り付け可）", height=280, key="text_import_body")
    if st.button("本文を解析", use_container_width=True):
        if not page_text.strip():
            st.warning("ページ本文を貼り付けてください。")
            return
        try:
            with st.spinner("本文を解析しています..."):
                results = import_from_page_text_bundle(
                    page_text,
                    default_source_url=source_url.strip(),
                    default_date=None if source_url.strip() else expected_date,
                )
            _set_import_preview(results)
            total_records = sum(len(result.records) for result in results)
            if len(results) == 1:
                st.success(f"{results[0].target_date} のデータを {total_records} 件解析しました。")
            else:
                st.success(f"{len(results)}日分のデータを {total_records} 件解析しました。")
        except AnaSloError as exc:
            st.error(exc.user_message)
            st.caption(str(exc))
        except Exception as exc:
            st.error("本文解析に失敗しました。")
            st.caption(str(exc))


def _render_preview(profile: dict) -> None:
    st.subheader("取得結果プレビュー・登録前確認")
    preview = st.session_state.get("import_preview")
    if not preview:
        st.info("URL取得またはHTML解析を実行すると、ここにプレビューが表示されます。")
        return
    target_dates = preview.get("target_dates") or [preview["target_date"]]
    if len(target_dates) > 1:
        date_label = f"{len(target_dates)}日分（{target_dates[0]}〜{target_dates[-1]}）"
    else:
        date_label = str(target_dates[0])
    st.write(f"対象日: {date_label} / 件数: {len(preview['records'])} / 方法: {preview.get('fetch_method')}")
    preview_df = _records_dataframe(preview["records"])
    st.dataframe(layout.style_diff_columns(preview_df, ["diff_coins"]), use_container_width=True, hide_index=True)
    confirm = st.checkbox("内容を確認しました。Supabaseへ登録します。")
    if st.button("データ登録", type="primary", disabled=not confirm, use_container_width=True):
        _save_preview(profile)


def _render_delete_tools() -> None:
    st.subheader("データ削除")
    c1, c2 = st.columns(2)
    with c1:
        target_date = st.date_input("指定日のデータ削除")
        confirm_date = st.checkbox("指定日の削除を確認", key="confirm_delete_date")
        if st.button("指定日を削除", disabled=not confirm_date, use_container_width=True):
            try:
                count = database.delete_records_by_date(target_date, st.session_state.get("access_token"), STORE_NAME)
                data_service.clear_data_cache()
                st.success(f"{target_date} のデータを {count} 件削除しました。")
            except Exception as exc:
                st.error("削除に失敗しました。")
                st.caption(str(exc))
    with c2:
        machine_no = st.number_input("指定台番号のデータ削除", min_value=0, max_value=99999, step=1)
        confirm_machine = st.checkbox("指定台番号の削除を確認", key="confirm_delete_machine")
        if st.button("指定台番号を削除", disabled=not confirm_machine, use_container_width=True):
            try:
                count = database.delete_records_by_machine(int(machine_no), st.session_state.get("access_token"), STORE_NAME)
                data_service.clear_data_cache()
                st.success(f"{int(machine_no)}番台のデータを {count} 件削除しました。")
            except Exception as exc:
                st.error("削除に失敗しました。")
                st.caption(str(exc))


def _render_calendar_tools(calendar_df: pd.DataFrame) -> None:
    st.subheader("特定日・イベントメモ")
    with st.form("calendar_form"):
        target_date = st.date_input("日付")
        special_day = st.checkbox("特定日として扱う")
        event_name = st.text_input("イベント名")
        memo = st.text_area("メモ")
        submitted = st.form_submit_button("特定日情報を保存", type="primary")
    if submitted:
        try:
            database.upsert_store_calendar(
                {
                    "store_name": STORE_NAME,
                    "date": target_date,
                    "special_day": special_day,
                    "event_name": event_name,
                    "memo": memo,
                },
                st.session_state.get("access_token"),
            )
            data_service.clear_data_cache()
            st.success("特定日情報を保存しました。")
        except Exception as exc:
            st.error("保存に失敗しました。")
            st.caption(str(exc))

    if not calendar_df.empty:
        st.dataframe(calendar_df.sort_values("date", ascending=False), use_container_width=True, hide_index=True)


def _render_csv_tools(df: pd.DataFrame) -> None:
    st.subheader("CSV入出力")
    if df.empty:
        st.info("エクスポートできるデータがありません。")
    else:
        csv = df.drop(columns=[col for col in ["date_only"] if col in df.columns]).to_csv(index=False).encode("utf-8-sig")
        st.download_button("CSVエクスポート", data=csv, file_name="machine_records.csv", mime="text/csv", use_container_width=True)

    uploaded = st.file_uploader("CSVインポート", type=["csv"], key="csv_import")
    if uploaded and st.button("CSVを登録", use_container_width=True):
        try:
            incoming = pd.read_csv(uploaded)
            required = {"store_name", "date", "machine_no", "machine_name", "games", "diff_coins"}
            missing = required - set(incoming.columns)
            if missing:
                st.error(f"必須列がありません: {', '.join(sorted(missing))}")
                return
            records = incoming.to_dict("records")
            summary = database.upsert_machine_records(records, st.session_state.get("access_token"))
            data_service.clear_data_cache()
            st.success(f"CSVを登録しました。追加 {summary['records_added']}件 / 更新 {summary['records_updated']}件")
        except Exception as exc:
            st.error("CSVインポートに失敗しました。")
            st.caption(str(exc))


def _render_logs() -> None:
    st.subheader("取得履歴・エラー履歴")
    try:
        logs = database.fetch_import_logs(st.session_state.get("access_token"), limit=200)
    except Exception as exc:
        st.error("履歴を取得できませんでした。")
        st.caption(str(exc))
        return
    logs_df = pd.DataFrame(logs)
    if logs_df.empty:
        st.info("取得履歴はまだありません。")
        return
    tab_all, tab_error = st.tabs(["取得履歴", "エラー履歴"])
    with tab_all:
        st.dataframe(logs_df, use_container_width=True, hide_index=True)
    with tab_error:
        errors = logs_df[logs_df["status"] == "error"] if "status" in logs_df else logs_df.iloc[0:0]
        st.dataframe(errors, use_container_width=True, hide_index=True)


def _render_registered_dates(df: pd.DataFrame) -> None:
    st.subheader("登録済み日付一覧")
    if df.empty:
        st.info("登録済みデータはありません。")
        return
    dates = (
        df.groupby("date_only")
        .agg(records=("machine_no", "count"), total_diff=("diff_coins", "sum"), avg_games=("games", "mean"))
        .reset_index()
        .sort_values("date_only", ascending=False)
    )
    st.dataframe(layout.style_diff_columns(dates, ["total_diff"]), use_container_width=True, hide_index=True)


def render(df, calendar_df, profile):
    auth.require_admin()
    st.title("管理画面")
    st.caption("1URLずつ手動実行する設計です。CAPTCHA回避やアクセス制限の不正な突破は行いません。")

    tab_import, tab_delete, tab_calendar, tab_csv, tab_logs = st.tabs(
        ["データ取込", "削除", "特定日編集", "CSV", "履歴"]
    )
    with tab_import:
        _render_url_import(profile)
        st.divider()
        _render_html_import()
        st.divider()
        _render_text_import()
        st.divider()
        _render_preview(profile)
        st.divider()
        _render_registered_dates(df)
    with tab_delete:
        _render_delete_tools()
    with tab_calendar:
        _render_calendar_tools(calendar_df)
    with tab_csv:
        _render_csv_tools(df)
    with tab_logs:
        _render_logs()
