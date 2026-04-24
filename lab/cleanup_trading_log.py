"""
lab/cleanup_trading_log.py
==========================
One-shot cleanup: remove 0xfake_* test pollution from lab/trading_log.json.

Background (Session 41)
-----------------------
tests/test_masterloop_e2e.py used to write fake paper trades (market_id
"0xfake_btc" / "0xfake_eth") directly into production lab/trading_log.json
because its fixtures didn't isolate the log path. Over months, 123 fake
rows accumulated and contaminated every "last N trades" accuracy window.

This script: loads the log, filters out any row whose market_id starts with
"0xfake", writes a timestamped backup, and rewrites the log with real trades
only. Preserves file structure and ordering of real trades.

Safety
------
- Backup written to lab/trading_log.json.pre-s41-cleanup.bak before any change.
- Does NOT delete the log.
- Does NOT touch rows with real (numeric or condition-id) market_ids.
- Idempotent: second run is a no-op if no 0xfake_ rows remain.
"""
from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path


LOG_PATH = Path(__file__).parent / "trading_log.json"
BACKUP_PATH = LOG_PATH.with_suffix(".json.pre-s41-cleanup.bak")


def _is_fake(trade: dict) -> bool:
    mid = str(trade.get("market_id", ""))
    return mid.startswith("0xfake")


def cleanup() -> dict:
    if not LOG_PATH.exists():
        return {"status": "no_log", "removed": 0, "kept": 0}

    raw = LOG_PATH.read_text()
    data = json.loads(raw)
    trades = data.get("trades", [])

    fake_rows = [t for t in trades if _is_fake(t)]
    real_rows = [t for t in trades if not _is_fake(t)]

    if not fake_rows:
        return {"status": "clean", "removed": 0, "kept": len(real_rows)}

    # Backup before writing
    shutil.copy2(LOG_PATH, BACKUP_PATH)

    data["trades"] = real_rows
    data["total_trades"] = len(real_rows)
    data["updated_at"] = datetime.now(timezone.utc).isoformat()
    data["cleaned_at_s41"] = data["updated_at"]
    data["cleaned_removed"] = len(fake_rows)

    LOG_PATH.write_text(json.dumps(data, indent=2))

    return {
        "status": "cleaned",
        "removed": len(fake_rows),
        "kept": len(real_rows),
        "backup": str(BACKUP_PATH),
    }


if __name__ == "__main__":
    result = cleanup()
    print(f"Status  : {result['status']}")
    print(f"Removed : {result['removed']} fake rows")
    print(f"Kept    : {result['kept']} real rows")
    if result.get("backup"):
        print(f"Backup  : {result['backup']}")
