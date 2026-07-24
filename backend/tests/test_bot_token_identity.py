"""Tests for binding bot tokens to the correct public Telegram bot ID."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from main import _telegram_bot_id_from_token


class BotTokenIdentityTests(unittest.TestCase):
    def test_extracts_public_bot_id(self):
        self.assertEqual(
            _telegram_bot_id_from_token("123456789:abcdefghijklmnopqrstuvwxyzABCDEFGHI"),
            123456789,
        )

    def test_rejects_missing_secret_or_non_numeric_identity(self):
        self.assertIsNone(_telegram_bot_id_from_token("123456789:"))
        self.assertIsNone(_telegram_bot_id_from_token("other:secret"))
