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


def test_permission_checks():
    assert auth.can("admin", "import_data")
    assert auth.can("admin", "manage_users")
    assert auth.can("viewer", "view_analysis")
    assert not auth.can("viewer", "delete_data")
    assert not auth.can(None, "view_analysis")

