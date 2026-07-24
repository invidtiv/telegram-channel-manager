"""Short-lived, browser-driven Telegram user authorization flow."""

import asyncio
import math
import time
from dataclasses import dataclass
from typing import Callable, Optional

from telethon.errors import (
    AuthRestartError,
    FloodWaitError,
    PasswordHashInvalidError,
    PhoneCodeExpiredError,
    PhoneCodeInvalidError,
    PhoneNumberBannedError,
    PhoneNumberFloodError,
    PhoneNumberInvalidError,
    RPCError,
    SessionPasswordNeededError,
)

try:
    from .telethon_client import create_telegram_client, telegram_session_lock
except ImportError:
    from telethon_client import create_telegram_client, telegram_session_lock


AUTH_FLOW_TTL_SECONDS = 10 * 60
CODE_REQUEST_COOLDOWN_SECONDS = 30
CODE_REQUEST_WINDOW_SECONDS = 15 * 60
MAX_CODE_REQUESTS_PER_WINDOW = 5
MAX_SUBMISSION_ATTEMPTS = 5


class TelegramAuthError(Exception):
    """A safe error suitable for returning from an authentication endpoint."""

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        retry_after: Optional[int] = None,
    ):
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.retry_after = retry_after


@dataclass
class _PendingAuthorization:
    phone: str
    phone_code_hash: str
    expires_at: float
    state: str = "code_required"
    submission_attempts: int = 0


class TelegramAuthManager:
    """Coordinates one local Telegram authorization attempt at a time."""

    def __init__(
        self,
        client_factory: Callable = create_telegram_client,
        lock: asyncio.Lock = telegram_session_lock,
        clock: Callable[[], float] = time.monotonic,
    ):
        self._client_factory = client_factory
        self._lock = lock
        self._clock = clock
        self._pending: Optional[_PendingAuthorization] = None
        self._request_times: list[float] = []

    def _clear_expired(self) -> None:
        if self._pending and self._pending.expires_at <= self._clock():
            self._pending = None

    def _status(self, authorized: bool) -> dict:
        if authorized:
            return {
                "authorized": True,
                "state": "authorized",
                "message": "Telegram is connected.",
                "expires_in": None,
            }

        self._clear_expired()
        if not self._pending:
            return {
                "authorized": False,
                "state": "phone_required",
                "message": "Telegram authorization is required.",
                "expires_in": None,
            }

        expires_in = max(0, int(self._pending.expires_at - self._clock()))
        if self._pending.state == "password_required":
            message = "Enter your Telegram two-step verification password."
        else:
            message = "Enter the code Telegram sent to your account."
        return {
            "authorized": False,
            "state": self._pending.state,
            "message": message,
            "expires_in": expires_in,
        }

    async def _disconnect(self, client) -> None:
        try:
            await client.disconnect()
        except Exception:
            pass

    def _new_client(self):
        try:
            return self._client_factory()
        except (TypeError, ValueError, RuntimeError) as exc:
            raise TelegramAuthError(
                503,
                "telegram_not_configured",
                "Telegram API credentials are not configured on the server.",
            ) from exc

    async def _get_status_locked(self) -> dict:
        client = self._new_client()
        try:
            await client.connect()
            authorized = await client.is_user_authorized()
            if authorized:
                self._pending = None
            return self._status(authorized)
        except RPCError as exc:
            raise TelegramAuthError(
                502,
                "telegram_unavailable",
                "Could not check Telegram authorization right now.",
            ) from exc
        finally:
            await self._disconnect(client)

    async def get_status(self) -> dict:
        async with self._lock:
            return await self._get_status_locked()

    def _check_request_rate_limit(self) -> None:
        now = self._clock()
        window_start = now - CODE_REQUEST_WINDOW_SECONDS
        self._request_times = [
            request_time
            for request_time in self._request_times
            if request_time > window_start
        ]

        if self._request_times:
            retry_after = math.ceil(
                CODE_REQUEST_COOLDOWN_SECONDS - (now - self._request_times[-1])
            )
            if retry_after > 0:
                raise TelegramAuthError(
                    429,
                    "code_request_cooldown",
                    f"Wait {retry_after} seconds before requesting another code.",
                    retry_after=retry_after,
                )

        if len(self._request_times) >= MAX_CODE_REQUESTS_PER_WINDOW:
            retry_after = max(1, int(self._request_times[0] + CODE_REQUEST_WINDOW_SECONDS - now))
            raise TelegramAuthError(
                429,
                "too_many_code_requests",
                "Too many code requests. Try again later.",
                retry_after=retry_after,
            )

    async def request_code(self, phone: str) -> dict:
        async with self._lock:
            self._clear_expired()
            client = self._new_client()
            try:
                await client.connect()
                if await client.is_user_authorized():
                    self._pending = None
                    return self._status(True)

                self._check_request_rate_limit()
                self._request_times.append(self._clock())
                sent_code = await client.send_code_request(phone)
                self._pending = _PendingAuthorization(
                    phone=phone,
                    phone_code_hash=sent_code.phone_code_hash,
                    expires_at=self._clock() + AUTH_FLOW_TTL_SECONDS,
                )
                return self._status(False)
            except PhoneNumberInvalidError as exc:
                raise TelegramAuthError(
                    400,
                    "invalid_phone",
                    "Telegram rejected that phone number. Use the full international number.",
                ) from exc
            except PhoneNumberBannedError as exc:
                raise TelegramAuthError(
                    403,
                    "phone_banned",
                    "Telegram has restricted this phone number.",
                ) from exc
            except (PhoneNumberFloodError, FloodWaitError) as exc:
                retry_after = max(1, int(getattr(exc, "seconds", 60)))
                raise TelegramAuthError(
                    429,
                    "telegram_rate_limit",
                    "Telegram rate-limited code requests. Try again later.",
                    retry_after=retry_after,
                ) from exc
            except AuthRestartError as exc:
                raise TelegramAuthError(
                    409,
                    "auth_restart_required",
                    "Telegram restarted authorization. Request a new code.",
                ) from exc
            except RPCError as exc:
                raise TelegramAuthError(
                    502,
                    "telegram_rejected_request",
                    "Telegram could not send a verification code.",
                ) from exc
            finally:
                await self._disconnect(client)

    def _require_pending(self, expected_state: str) -> _PendingAuthorization:
        self._clear_expired()
        if not self._pending:
            raise TelegramAuthError(
                410,
                "auth_flow_expired",
                "The authorization attempt expired. Request a new code.",
            )
        if self._pending.state != expected_state:
            raise TelegramAuthError(
                409,
                "wrong_auth_step",
                "Complete the current authorization step first.",
            )
        return self._pending

    def _record_failed_submission(self, pending: _PendingAuthorization) -> None:
        pending.submission_attempts += 1
        if pending.submission_attempts >= MAX_SUBMISSION_ATTEMPTS:
            self._pending = None
            raise TelegramAuthError(
                429,
                "too_many_attempts",
                "Too many failed attempts. Request a new code.",
            )

    async def submit_code(self, code: str) -> dict:
        async with self._lock:
            pending = self._require_pending("code_required")
            client = self._new_client()
            try:
                await client.connect()
                await client.sign_in(
                    phone=pending.phone,
                    code=code,
                    phone_code_hash=pending.phone_code_hash,
                )
                if not await client.is_user_authorized():
                    raise TelegramAuthError(
                        401,
                        "authorization_incomplete",
                        "Telegram authorization did not complete.",
                    )
                self._pending = None
                return self._status(True)
            except SessionPasswordNeededError:
                pending.state = "password_required"
                pending.submission_attempts = 0
                return self._status(False)
            except PhoneCodeInvalidError as exc:
                self._record_failed_submission(pending)
                raise TelegramAuthError(
                    400,
                    "invalid_code",
                    "The Telegram verification code is invalid.",
                ) from exc
            except PhoneCodeExpiredError as exc:
                self._pending = None
                raise TelegramAuthError(
                    410,
                    "code_expired",
                    "The Telegram verification code expired. Request a new code.",
                ) from exc
            except TelegramAuthError:
                raise
            except RPCError as exc:
                raise TelegramAuthError(
                    502,
                    "telegram_rejected_code",
                    "Telegram could not verify the code.",
                ) from exc
            finally:
                await self._disconnect(client)

    async def submit_password(self, password: str) -> dict:
        async with self._lock:
            pending = self._require_pending("password_required")
            client = self._new_client()
            try:
                await client.connect()
                await client.sign_in(password=password)
                if not await client.is_user_authorized():
                    raise TelegramAuthError(
                        401,
                        "authorization_incomplete",
                        "Telegram authorization did not complete.",
                    )
                self._pending = None
                return self._status(True)
            except PasswordHashInvalidError as exc:
                self._record_failed_submission(pending)
                raise TelegramAuthError(
                    400,
                    "invalid_password",
                    "The Telegram two-step verification password is invalid.",
                ) from exc
            except TelegramAuthError:
                raise
            except RPCError as exc:
                raise TelegramAuthError(
                    502,
                    "telegram_rejected_password",
                    "Telegram could not verify the password.",
                ) from exc
            finally:
                await self._disconnect(client)

    async def cancel(self) -> dict:
        async with self._lock:
            self._pending = None
            return await self._get_status_locked()
