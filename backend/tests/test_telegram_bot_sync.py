"""Tests for owned-bot matching and tokenless registry creation."""

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from database import Base
from models import Bot, BotAccount, TelegramAccount
from telegram_bot_sync import TelegramBotSync


class _FakeTelegramClient:
    def __init__(self):
        self.users = [
            SimpleNamespace(
                id=111111111,
                username="ExistingBot",
                first_name="Existing",
                last_name="Bot",
                bot_nochats=False,
                bot_inline=True,
                bot_inline_placeholder="Search",
                bot_inline_geo=False,
                bot_business=False,
            ),
            SimpleNamespace(
                id=222222222,
                username="NewOwnedBot",
                first_name="New",
                last_name="Owned Bot",
                bot_nochats=False,
                bot_inline=False,
                bot_inline_placeholder="",
                bot_inline_geo=False,
                bot_business=False,
            ),
        ]

    async def connect(self):
        return None

    async def disconnect(self):
        return None

    async def is_user_authorized(self):
        return True

    async def get_me(self):
        return SimpleNamespace(
            id=999,
            username="owner",
            first_name="Account",
            last_name="Owner",
            phone="491234567890",
        )

    async def __call__(self, request):
        request_name = type(request).__name__
        if request_name == "GetAdminedBotsRequest":
            return self.users
        if request_name == "GetBotInfoRequest":
            bot_id = request.bot.id if hasattr(request.bot, "id") else request.bot
            return SimpleNamespace(
                name="Existing Name" if bot_id == 111111111 else "New Name",
                about="Current about",
                description="Current description",
            )
        if request_name == "GetFullUserRequest":
            return SimpleNamespace(
                full_user=SimpleNamespace(
                    bot_info=SimpleNamespace(
                        commands=[SimpleNamespace(command="start", description="Start bot")],
                    ),
                ),
            )
        raise AssertionError(f"Unexpected Telegram request: {request_name}")


class TelegramBotSyncTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)

    async def asyncTearDown(self):
        await self.engine.dispose()

    async def test_matches_existing_bot_and_creates_tokenless_bot(self):
        async with self.sessions() as db:
            db.add(TelegramAccount(
                id="account-one",
                label="One",
                country_code="DE",
                session_name="account_test",
            ))
            db.add(Bot(
                id="existing",
                telegram_bot_id=111111111,
                token="111111111:abcdefghijklmnopqrstuvwxyzABCDEFGHI",
                username="old_username",
                display_name="Old name",
                settings={},
            ))
            await db.commit()

            fake_client = _FakeTelegramClient()
            sync = TelegramBotSync(
                db,
                "account-one",
                "account_test",
                client_factory=lambda _session_name: fake_client,
            )
            result = await sync.run()

            self.assertEqual(result["found"], 2)
            self.assertEqual(result["matched"], 1)
            self.assertEqual(result["created"], 1)
            self.assertEqual(result["token_missing"], 1)

            bots = (await db.execute(select(Bot).order_by(Bot.telegram_bot_id))).scalars().all()
            self.assertEqual(len(bots), 2)
            self.assertEqual(bots[0].token, "111111111:abcdefghijklmnopqrstuvwxyzABCDEFGHI")
            self.assertEqual(bots[0].username, "ExistingBot")
            self.assertEqual(bots[1].token, "")
            self.assertEqual(bots[1].username, "NewOwnedBot")

            links = (await db.execute(select(BotAccount))).scalars().all()
            self.assertEqual({link.bot_id for link in links}, {bot.id for bot in bots})
