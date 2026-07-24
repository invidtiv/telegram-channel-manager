"""Import BotFather chat history into Personal Telegram bot registry.

Parses Telegram Desktop exported JSON chat history with BotFather and extracts
created bots (username + token) from the /newbot confirmation messages.

Usage:
    python backend/import_botfather.py /path/to/botfather_export.json
    python backend/import_botfather.py  # uses botfather.json in project root
"""

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database import AsyncSessionLocal, init_db
from main import import_bots
from botfather_parser import parse_botfather_history

DEFAULT_BOTFATHER_PATHS = [
    "botfather.json",
    "data/botfather.json",
]


def read_botfather_json(path: str):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def find_botfather_file(args):
    if args.path:
        return args.path
    for path in DEFAULT_BOTFATHER_PATHS:
        full = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), path)
        if os.path.exists(full):
            return full
        if os.path.exists(path):
            return path
    return None


async def main():
    parser = argparse.ArgumentParser(description="Import BotFather chat history into bot registry")
    parser.add_argument("path", nargs="?", help="Path to botfather_export.json")
    parser.add_argument("--dry-run", action="store_true", help="Print bots without importing")
    parser.add_argument("--project", default="botfather", help="Project name for imported bots")
    args = parser.parse_args()

    path = find_botfather_file(args)
    if not path:
        print("No botfather.json found. Provide a path or place botfather.json in the project root.")
        sys.exit(1)

    print(f"Using source: {path}")
    data = read_botfather_json(path)
    parsed = parse_botfather_history(data)
    bots = parsed["bots"]
    deleted_usernames = parsed["deleted_usernames"]
    print(f"Found {len(bots)} bot(s) in BotFather history.")
    print(f"Found {len(deleted_usernames)} deletion event(s).")

    if args.dry_run:
        for bot in bots:
            print(f"  - @{bot['username']} ({bot['token'][:20]}...)")
        for username in deleted_usernames:
            print(f"  - DELETED @{username}")
        return

    if args.project:
        for bot in bots:
            bot["project"] = args.project

    await init_db()
    async with AsyncSessionLocal() as db:
        result = await import_bots({"bots": bots}, db)
        print(f"Imported {result.added} bot(s), skipped {result.skipped} existing.")

        if deleted_usernames:
            from sqlalchemy import select
            from models import Bot
            removed = 0
            for username in deleted_usernames:
                bot_result = await db.execute(select(Bot).where(Bot.username == username).limit(1))
                bot = bot_result.scalar_one_or_none()
                if bot:
                    bot.status = "deleted"
                    bot.updated_at = datetime.utcnow()
                    removed += 1
            await db.commit()
            print(f"Marked {removed} bot(s) as deleted.")

        if result.errors:
            print("Errors:")
            for err in result.errors:
                print(f"  - {err}")


if __name__ == "__main__":
    asyncio.run(main())
