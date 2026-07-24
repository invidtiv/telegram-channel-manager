"""Synchronize bots owned by one Telegram account into the local registry."""

import uuid
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from telethon.errors import (
    AuthKeyUnregisteredError,
    FloodWaitError,
    RPCError,
    SessionRevokedError,
    UserDeactivatedError,
)
from telethon.tl.functions.bots import GetAdminedBotsRequest, GetBotInfoRequest
from telethon.tl.functions.users import GetFullUserRequest

from models import Bot, BotAccount, BotCommand, TelegramAccount
from telethon_client import create_telegram_client, get_session_lock


class TelegramAuthorizationRequired(RuntimeError):
    """The account session must be authorized again."""


def _text(value) -> str:
    return value if isinstance(value, str) else ""


def _display_name(user) -> str:
    return " ".join(
        part for part in (_text(getattr(user, "first_name", "")), _text(getattr(user, "last_name", "")))
        if part
    )


def _command_rows(bot_info) -> list[dict]:
    return [
        {
            "command": _text(getattr(command, "command", "")),
            "description": _text(getattr(command, "description", "")),
            "scope": "default",
            "language_code": None,
        }
        for command in (getattr(bot_info, "commands", None) or [])
        if getattr(command, "command", None)
    ]


class TelegramBotSync:
    """Refresh canonical bots and ownership links for one account."""

    def __init__(
        self,
        db: AsyncSession,
        account_id: str,
        session_name: str,
        client_factory=create_telegram_client,
    ):
        self.db = db
        self.account_id = account_id
        self.session_name = session_name
        self.client = client_factory(session_name)
        self.session_lock = get_session_lock(session_name)

    async def run(self) -> dict:
        async with self.session_lock:
            return await self._run_locked()

    async def _run_locked(self) -> dict:
        await self.client.connect()
        if not await self.client.is_user_authorized():
            await self.client.disconnect()
            raise TelegramAuthorizationRequired(
                "Telegram authorization is required for this account."
            )

        counts = {"found": 0, "matched": 0, "created": 0, "updated": 0, "token_missing": 0}
        seen_bot_ids: set[str] = set()
        try:
            users = list(await self.client(GetAdminedBotsRequest()))
            counts["found"] = len(users)

            for user in users:
                telegram_id = getattr(user, "id", None)

                username = _text(getattr(user, "username", "")) or f"bot_{telegram_id}"
                details = None
                try:
                    details = await self.client(GetBotInfoRequest(
                        lang_code="",
                        bot=user,
                    ))
                except RPCError:
                    pass
                full_bot_info = None
                try:
                    full_result = await self.client(GetFullUserRequest(user))
                    full_bot_info = getattr(
                        getattr(full_result, "full_user", None),
                        "bot_info",
                        None,
                    )
                except RPCError:
                    pass

                existing_result = await self.db.execute(
                    select(Bot).where(Bot.telegram_bot_id == telegram_id).limit(1)
                )
                bot = existing_result.scalar_one_or_none()
                if bot is None and username:
                    existing_result = await self.db.execute(
                        select(Bot).where(func.lower(Bot.username) == username.lower()).limit(1)
                    )
                    bot = existing_result.scalar_one_or_none()

                commands = _command_rows(full_bot_info or details)
                settings_patch = {
                    "can_join_groups": not bool(getattr(user, "bot_nochats", False)),
                    "supports_inline_queries": bool(getattr(user, "bot_inline", False)),
                    "inline_mode": bool(getattr(user, "bot_inline", False)),
                    "inline_placeholder": _text(getattr(user, "bot_inline_placeholder", "")),
                    "inline_geo_enabled": bool(getattr(user, "bot_inline_geo", False)),
                    "business_mode_enabled": bool(getattr(user, "bot_business", False)),
                }
                if full_bot_info is not None:
                    settings_patch["commands"] = commands

                if bot is None:
                    bot = Bot(
                        id=str(uuid.uuid4()),
                        telegram_bot_id=telegram_id,
                        token="",
                        username=username,
                        display_name=_text(getattr(details, "name", "")) or _display_name(user) or username,
                        description=_text(getattr(details, "description", "")),
                        about_text=_text(getattr(details, "about", "")),
                        project="",
                        environment="production",
                        status="active",
                        tags=["telegram-sync"],
                        notes="Discovered through Telegram owned-bot scan; token still needed.",
                        settings=settings_patch,
                    )
                    self.db.add(bot)
                    await self.db.flush()
                    counts["created"] += 1
                else:
                    counts["matched"] += 1
                    changed = False
                    updates = {
                        "telegram_bot_id": telegram_id,
                        "username": username,
                        "status": "active",
                    }
                    if details is not None:
                        updates.update({
                            "display_name": _text(getattr(details, "name", "")) or _display_name(user) or username,
                            "description": _text(getattr(details, "description", "")),
                            "about_text": _text(getattr(details, "about", "")),
                        })
                    for field, value in updates.items():
                        if getattr(bot, field) != value:
                            setattr(bot, field, value)
                            changed = True
                    merged_settings = dict(bot.settings or {})
                    merged_settings.update(settings_patch)
                    if merged_settings != (bot.settings or {}):
                        bot.settings = merged_settings
                        changed = True
                    if changed:
                        bot.updated_at = datetime.utcnow()
                        counts["updated"] += 1

                if not bot.token:
                    counts["token_missing"] += 1

                if full_bot_info is not None:
                    command_result = await self.db.execute(
                        select(BotCommand).where(BotCommand.bot_id == bot.id)
                    )
                    for command in command_result.scalars().all():
                        await self.db.delete(command)
                    for command in commands:
                        self.db.add(BotCommand(bot_id=bot.id, **command))

                link_result = await self.db.execute(
                    select(BotAccount).where(
                        BotAccount.account_id == self.account_id,
                        BotAccount.bot_id == bot.id,
                    )
                )
                link = link_result.scalar_one_or_none()
                if link:
                    link.last_seen_at = datetime.utcnow()
                else:
                    self.db.add(BotAccount(
                        account_id=self.account_id,
                        bot_id=bot.id,
                        last_seen_at=datetime.utcnow(),
                    ))
                seen_bot_ids.add(bot.id)

            stale_result = await self.db.execute(
                select(BotAccount).where(BotAccount.account_id == self.account_id)
            )
            for link in stale_result.scalars().all():
                if link.bot_id not in seen_bot_ids:
                    await self.db.delete(link)

            account_result = await self.db.execute(
                select(TelegramAccount).where(TelegramAccount.id == self.account_id)
            )
            account = account_result.scalar_one()
            me = await self.client.get_me()
            account.telegram_user_id = getattr(me, "id", None)
            account.username = getattr(me, "username", None)
            account.display_name = _display_name(me)
            account.phone_hint = _phone_hint(getattr(me, "phone", ""))
            account.last_bot_scan_at = datetime.utcnow()
            account.updated_at = datetime.utcnow()
            await self.db.commit()
            return counts
        except FloodWaitError as error:
            await self.db.rollback()
            raise RuntimeError(f"Telegram rate-limited the scan. Wait {error.seconds} seconds.") from error
        except (AuthKeyUnregisteredError, SessionRevokedError, UserDeactivatedError) as error:
            await self.db.rollback()
            raise TelegramAuthorizationRequired(
                "The Telegram session expired or was revoked. Authorize this account again."
            ) from error
        except RPCError as error:
            await self.db.rollback()
            raise RuntimeError("Telegram could not complete the owned-bot scan.") from error
        finally:
            await self.client.disconnect()


def _phone_hint(phone: str) -> str:
    """Return only enough of a phone number to distinguish accounts."""
    digits = "".join(character for character in (phone or "") if character.isdigit())
    return f"••••{digits[-4:]}" if digits else ""
