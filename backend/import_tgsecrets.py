"""Import TGsecrets bot registry into Personal Telegram database.

Usage:
    python backend/import_tgsecrets.py --sqlite /path/to/tg-registry.sqlite
    python backend/import_tgsecrets.py --json /path/to/tg-registry-export.json
    python backend/import_tgsecrets.py --json /home/bsdev/TS/TGsecrets/registry.sample.json

If no source is provided, it looks for the TGsecrets SQLite database at the
common Docker volume location /home/bsdev/TS/TGsecrets/tg-registry.sqlite
and then at the sample registry.
"""

import argparse
import asyncio
import json
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database import AsyncSessionLocal, init_db
from schemas import BotCreate
from main import create_bot, import_bots


TGSECRETS_SQLITE_DEFAULTS = [
    "/home/bsdev/TS/TGsecrets/tg-registry.sqlite",
    "/home/bsdev/TS/TGsecrets/data/tg-registry.sqlite",
    "/app/data/tg-registry.sqlite",
]

TGSECRETS_JSON_DEFAULTS = [
    "/home/bsdev/TS/TGsecrets/registry.sample.json",
    "/home/bsdev/TS/TGsecrets/tg-registry-export.json",
]


def _read_sqlite(path: str):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    row = cursor.execute("SELECT data FROM registry WHERE id = 1").fetchone()
    conn.close()
    if not row:
        return None
    return json.loads(row["data"])


def _read_json(path: str):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _find_source(args):
    if args.sqlite:
        return _read_sqlite(args.sqlite)
    if args.json:
        return _read_json(args.json)

    for path in TGSECRETS_SQLITE_DEFAULTS:
        if os.path.exists(path):
            print(f"Using SQLite source: {path}")
            return _read_sqlite(path)

    for path in TGSECRETS_JSON_DEFAULTS:
        if os.path.exists(path):
            print(f"Using JSON source: {path}")
            return _read_json(path)

    return None


async def main():
    parser = argparse.ArgumentParser(description="Import TGsecrets bot registry into Personal Telegram")
    parser.add_argument("--sqlite", help="Path to tg-registry.sqlite")
    parser.add_argument("--json", help="Path to TGsecrets registry JSON export")
    parser.add_argument("--dry-run", action="store_true", help="Print bots without importing")
    args = parser.parse_args()

    data = _find_source(args)
    if data is None:
        print("No TGsecrets source found. Provide --sqlite or --json.")
        sys.exit(1)

    bots = data.get("bots", []) if isinstance(data, dict) else data
    if not isinstance(bots, list):
        print("Invalid registry: 'bots' must be an array.")
        sys.exit(1)

    print(f"Found {len(bots)} bot(s) to import.")
    if args.dry_run:
        for bot in bots:
            print(f"  - {bot.get('username', 'unknown')} ({bot.get('project', 'no-project')})")
        return

    await init_db()
    async with AsyncSessionLocal() as db:
        result = await import_bots({"bots": bots}, db)
        print(f"Imported {result.added} bot(s), skipped {result.skipped} existing.")
        if result.errors:
            print("Errors:")
            for err in result.errors:
                print(f"  - {err}")


if __name__ == "__main__":
    asyncio.run(main())
