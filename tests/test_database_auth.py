from __future__ import annotations

import auth
import database


def test_compute_upsert_summary_counts_added_and_updated():
    existing = [
        {"store_name": "マルハン綾瀬上土棚店", "date": "2026-07-07", "machine_no": 601},
        {"store_name": "マルハン綾瀬上土棚店", "date": "2026-07-07", "machine_no": 602},
    ]
    incoming = [
        {"store_name": "マルハン綾瀬上土棚店", "date": "2026-07-07", "machine_no": 601, "machine_name": "A", "games": 1, "diff_coins": 1},
        {"store_name": "マルハン綾瀬上土棚店", "date": "2026-07-07", "machine_no": 603, "machine_name": "B", "games": 1, "diff_coins": 1},
    ]
    summary = database.compute_upsert_summary(existing, incoming)
    assert summary == {"records_added": 1, "records_updated": 1, "records_total": 2}


def test_dedupe_payloads_keeps_latest_duplicate_record():
    incoming = [
        {"store_name": "マルハン綾瀬上土棚店", "date": "2026-07-07", "machine_no": 601, "machine_name": "A", "games": 1000, "diff_coins": 100},
        {"store_name": "マルハン綾瀬上土棚店", "date": "2026-07-07", "machine_no": 601, "machine_name": "A", "games": 2000, "diff_coins": 500},
        {"store_name": "マルハン綾瀬上土棚店", "date": "2026-07-07", "machine_no": 602, "machine_name": "B", "games": 3000, "diff_coins": -100},
    ]
    payloads = database.dedupe_record_payloads(incoming)
    assert len(payloads) == 2
    record_601 = next(row for row in payloads if row["machine_no"] == 601)
    assert record_601["games"] == 2000
    assert record_601["diff_coins"] == 500

    summary = database.compute_upsert_summary([], incoming)
    assert summary == {"records_added": 2, "records_updated": 0, "records_total": 2}


def test_permission_checks():
    assert auth.can("admin", "import_data")
    assert auth.can("admin", "manage_users")
    assert auth.can("viewer", "view_analysis")
    assert not auth.can("viewer", "delete_data")
    assert not auth.can(None, "view_analysis")
