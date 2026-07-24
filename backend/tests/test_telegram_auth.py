"""Focused tests for the browser-driven Telegram authorization state machine."""

import asyncio
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

from telethon.errors import (
    PasswordHashInvalidError,
    PhoneCodeInvalidError,
    SessionPasswordNeededError,
)

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from schemas import TelegramCodeRequest, TelegramPhoneRequest
from telegram_auth import TelegramAuthError, TelegramAuthManager


class _Clock:
    def __init__(self):
        self.value = 100.0

    def __call__(self):
        return self.value


class _TelegramState:
    def __init__(self, require_password=False):
        self.authorized = False
        self.require_password = require_password
        self.sent_phone = None
        self.connect_count = 0
        self.disconnect_count = 0


class _FakeTelegramClient:
    def __init__(self, state):
        self.state = state

    async def connect(self):
        self.state.connect_count += 1

    async def disconnect(self):
        self.state.disconnect_count += 1

    async def is_user_authorized(self):
        return self.state.authorized

    async def send_code_request(self, phone):
        self.state.sent_phone = phone
        return SimpleNamespace(phone_code_hash="server-side-code-hash")

    async def sign_in(self, **kwargs):
        if "password" in kwargs:
            if kwargs["password"] != "correct password":
                raise PasswordHashInvalidError(request=None)
            self.state.authorized = True
            return

        if kwargs.get("code") != "12345":
            raise PhoneCodeInvalidError(request=None)
        if self.state.require_password:
            raise SessionPasswordNeededError(request=None)
        self.state.authorized = True


class TelegramAuthManagerTests(unittest.IsolatedAsyncioTestCase):
    def make_manager(self, state=None, clock=None):
        state = state or _TelegramState()
        clock = clock or _Clock()
        manager = TelegramAuthManager(
            client_factory=lambda: _FakeTelegramClient(state),
            lock=asyncio.Lock(),
            clock=clock,
        )
        return manager, state, clock

    async def test_phone_and_code_authorize_session(self):
        manager, state, _ = self.make_manager()

        initial = await manager.get_status()
        waiting = await manager.request_code("+491234567890")
        complete = await manager.submit_code("12345")

        self.assertEqual(initial["state"], "phone_required")
        self.assertEqual(waiting["state"], "code_required")
        self.assertEqual(state.sent_phone, "+491234567890")
        self.assertTrue(complete["authorized"])
        self.assertEqual(complete["state"], "authorized")
        self.assertEqual(state.connect_count, state.disconnect_count)

    async def test_two_step_password_is_supported_without_storing_password(self):
        manager, _, _ = self.make_manager(_TelegramState(require_password=True))

        await manager.request_code("+491234567890")
        password_step = await manager.submit_code("12345")
        complete = await manager.submit_password("correct password")

        self.assertEqual(password_step["state"], "password_required")
        self.assertTrue(complete["authorized"])
        self.assertFalse(hasattr(manager._pending, "password"))

    async def test_invalid_code_returns_safe_error_and_allows_retry(self):
        manager, _, _ = self.make_manager()
        await manager.request_code("+491234567890")

        with self.assertRaises(TelegramAuthError) as raised:
            await manager.submit_code("99999")

        self.assertEqual(raised.exception.status_code, 400)
        self.assertEqual(raised.exception.code, "invalid_code")
        self.assertNotIn("99999", raised.exception.message)
        self.assertTrue((await manager.submit_code("12345"))["authorized"])

    async def test_expired_attempt_requires_new_code(self):
        manager, _, clock = self.make_manager()
        await manager.request_code("+491234567890")
        clock.value += 601

        with self.assertRaises(TelegramAuthError) as raised:
            await manager.submit_code("12345")

        self.assertEqual(raised.exception.status_code, 410)
        self.assertEqual(raised.exception.code, "auth_flow_expired")

    async def test_code_requests_have_a_cooldown(self):
        manager, _, _ = self.make_manager()
        await manager.request_code("+491234567890")

        with self.assertRaises(TelegramAuthError) as raised:
            await manager.request_code("+491234567890")

        self.assertEqual(raised.exception.status_code, 429)
        self.assertGreater(raised.exception.retry_after, 0)

    async def test_cancel_clears_attempt_without_signing_out_authorized_session(self):
        manager, state, _ = self.make_manager()
        state.authorized = True

        result = await manager.cancel()

        self.assertTrue(result["authorized"])
        self.assertEqual(result["state"], "authorized")


class TelegramAuthSchemaTests(unittest.TestCase):
    def test_phone_and_code_are_normalized(self):
        self.assertEqual(
            TelegramPhoneRequest(phone="+49 (123) 456-7890").phone,
            "+491234567890",
        )
        self.assertEqual(TelegramCodeRequest(code="12 345").code, "12345")

    def test_invalid_phone_is_rejected(self):
        with self.assertRaises(ValueError):
            TelegramPhoneRequest(phone="0049-not-a-number")


if __name__ == "__main__":
    unittest.main()
