"""Regression tests for the backward-compatible account migration."""

import sys
import unittest
from pathlib import Path

from sqlalchemy import create_engine, inspect, select
from sqlalchemy.orm import Session

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from database import Base, _migrate_bot_identity, _seed_default_account
from models import Bot, BotAccount, TelegramAccount


class AccountMigrationTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)

    def tearDown(self):
        self.engine.dispose()

    def test_seed_does_not_restore_associations_removed_by_a_scan(self):
        with Session(self.engine) as session:
            session.add(Bot(id="bot-one", token="", username="one"))
            session.commit()

        with self.engine.begin() as connection:
            _seed_default_account(connection)

        with Session(self.engine) as session:
            link = session.scalar(select(BotAccount))
            self.assertIsNotNone(link)
            session.delete(link)
            session.commit()

        with self.engine.begin() as connection:
            _seed_default_account(connection)

        with Session(self.engine) as session:
            self.assertIsNotNone(session.get(TelegramAccount, "default"))
            self.assertIsNone(session.scalar(select(BotAccount)))

    def test_only_one_duplicate_registry_row_gets_canonical_telegram_id(self):
        token = "123456789:abcdefghijklmnopqrstuvwxyzABCDEFGHI"
        with Session(self.engine) as session:
            session.add_all([
                Bot(id="bot-one", token=token, username="one"),
                Bot(id="bot-two", token=token, username="two"),
            ])
            session.commit()

        with self.engine.begin() as connection:
            _migrate_bot_identity(connection)

        with Session(self.engine) as session:
            bots = session.scalars(select(Bot)).all()
            self.assertEqual(
                [bot.telegram_bot_id for bot in bots].count(123456789),
                1,
            )
        indexes = inspect(self.engine).get_indexes("bots")
        telegram_id_index = next(
            index for index in indexes if index["name"] == "ix_bots_telegram_bot_id"
        )
        self.assertTrue(telegram_id_index["unique"])
