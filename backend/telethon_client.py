"""Telegram client for ingesting channels into database."""

import os
import asyncio
from typing import Dict, Any
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from telethon import TelegramClient
from telethon.tl.types import (
    Channel, Chat,
    UserStatusOnline, UserStatusOffline, UserStatusRecently,
    UserStatusLastWeek, UserStatusLastMonth, UserStatusEmpty,
)
from telethon.tl.functions.messages import GetFullChatRequest
from telethon.errors import FloodWaitError, RPCError, ChatAdminRequiredError

from models import Channel as ChannelModel, ChannelAccount, GroupMember, TelegramAccount


telegram_session_lock = asyncio.Lock()
_session_locks: dict[str, asyncio.Lock] = {}


def get_telegram_session_path(session_name: str | None = None) -> str:
    """Return the configured Telethon session path."""
    session_name = session_name or os.getenv('SESSION_NAME', 'list_channels_session')
    if session_name == os.getenv('SESSION_NAME', 'list_channels_session'):
        return os.path.join(os.path.dirname(os.path.abspath(__file__)), session_name)
    if not session_name.startswith("account_") or not session_name.replace("_", "").isalnum():
        raise RuntimeError("Invalid Telegram session identifier")
    session_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "sessions")
    os.makedirs(session_dir, mode=0o700, exist_ok=True)
    return os.path.join(session_dir, session_name)


def create_telegram_client(session_name: str | None = None) -> TelegramClient:
    """Create a Telegram client using server-side credentials and session storage."""
    api_id = os.getenv('TELEGRAM_API_ID')
    api_hash = os.getenv('TELEGRAM_API_HASH')
    if not api_id or not api_hash:
        raise RuntimeError("Telegram API credentials are not configured")
    return TelegramClient(get_telegram_session_path(session_name), int(api_id), api_hash)


def get_session_lock(session_name: str | None = None) -> asyncio.Lock:
    """Return a process-local lock for one session file."""
    key = session_name or os.getenv('SESSION_NAME', 'list_channels_session')
    if key == os.getenv('SESSION_NAME', 'list_channels_session'):
        return telegram_session_lock
    return _session_locks.setdefault(key, asyncio.Lock())


class TelegramIngestion:
    """Handles ingestion of Telegram channels into the database."""
    
    def __init__(self, db: AsyncSession, account_id: str = "default", session_name: str | None = None):
        self.db = db
        self.account_id = account_id
        self.session_name = session_name
        self.client = create_telegram_client(session_name)
        self.session_lock = get_session_lock(session_name)

    async def run_ingestion(self, status_dict: Dict[str, Any]) -> Dict[str, int]:
        """Run ingestion while holding exclusive access to the session file."""
        async with self.session_lock:
            return await self._run_ingestion_locked(status_dict)

    async def _run_ingestion_locked(self, status_dict: Dict[str, Any]) -> Dict[str, int]:
        """Run the full ingestion process."""
        await self.client.connect()
        
        if not await self.client.is_user_authorized():
            await self.client.disconnect()
            raise Exception("User not authorized. Please authenticate first.")
        
        try:
            # Get all dialogs
            status_dict["message"] = "Fetching dialogs from Telegram..."
            dialogs = await self.client.get_dialogs(limit=None)
            
            # Filter to channels and groups only
            channel_dialogs = [
                d for d in dialogs 
                if isinstance(d.entity, (Channel, Chat))
            ]
            
            status_dict["total"] = len(channel_dialogs)
            status_dict["processed"] = 0
            
            added = 0
            updated = 0
            seen_channel_ids = set()
            
            for dialog in channel_dialogs:
                entity = dialog.entity
                seen_channel_ids.add(entity.id)
                status_dict["message"] = f"Processing: {dialog.name}"
                
                # Calculate bot_chat_id
                if isinstance(entity, Channel):
                    if entity.megagroup:
                        channel_type = "supergroup"
                    else:
                        channel_type = "channel"
                    bot_chat_id = f"-100{entity.id}"
                else:  # Chat
                    channel_type = "group"
                    bot_chat_id = f"-{entity.id}"
                
                # Get participant count
                participants_count = getattr(entity, 'participants_count', None)
                
                # Check if channel already exists
                existing = await self.db.execute(
                    select(ChannelModel).where(ChannelModel.id == entity.id)
                )
                existing_channel = existing.scalar_one_or_none()
                
                if existing_channel:
                    # Update existing channel
                    existing_channel.name = dialog.name or "Unknown"
                    existing_channel.bot_chat_id = bot_chat_id
                    existing_channel.username = getattr(entity, 'username', None)
                    existing_channel.type = channel_type
                    existing_channel.participants_count = participants_count
                    existing_channel.is_verified = getattr(entity, 'verified', False)
                    existing_channel.is_megagroup = getattr(entity, 'megagroup', False)
                    existing_channel.updated_at = datetime.utcnow()
                    updated += 1
                else:
                    # Create new channel
                    new_channel = ChannelModel(
                        id=entity.id,
                        bot_chat_id=bot_chat_id,
                        name=dialog.name or "Unknown",
                        username=getattr(entity, 'username', None),
                        type=channel_type,
                        participants_count=participants_count,
                        is_verified=getattr(entity, 'verified', False),
                        is_megagroup=getattr(entity, 'megagroup', False),
                    )
                    self.db.add(new_channel)
                    added += 1

                link_result = await self.db.execute(
                    select(ChannelAccount).where(
                        ChannelAccount.account_id == self.account_id,
                        ChannelAccount.channel_id == entity.id,
                    )
                )
                link = link_result.scalar_one_or_none()
                if link:
                    link.last_seen_at = datetime.utcnow()
                else:
                    self.db.add(ChannelAccount(
                        account_id=self.account_id,
                        channel_id=entity.id,
                        last_seen_at=datetime.utcnow(),
                    ))
                
                status_dict["processed"] += 1
                
                # Commit every 10 channels to avoid large transactions
                if (added + updated) % 10 == 0:
                    await self.db.commit()
                
                # Small delay to avoid rate limits
                await asyncio.sleep(0.2)
            
            # Final commit
            stale_links = await self.db.execute(
                select(ChannelAccount).where(ChannelAccount.account_id == self.account_id)
            )
            for link in stale_links.scalars().all():
                if link.channel_id not in seen_channel_ids:
                    await self.db.delete(link)
            account_result = await self.db.execute(
                select(TelegramAccount).where(TelegramAccount.id == self.account_id)
            )
            account = account_result.scalar_one_or_none()
            if account:
                account.last_channel_scan_at = datetime.utcnow()
            await self.db.commit()
            
            return {
                "channels_added": added,
                "channels_updated": updated
            }
            
        except FloodWaitError as e:
            await self.db.rollback()
            raise Exception(f"Rate limited by Telegram. Wait {e.seconds} seconds.")
        except RPCError as e:
            await self.db.rollback()
            raise Exception(f"Telegram API error: {e}")
        finally:
            await self.client.disconnect()

    @staticmethod
    def _get_user_status(status) -> str:
        """Convert Telethon UserStatus to string."""
        if isinstance(status, UserStatusOnline):
            return "online"
        elif isinstance(status, UserStatusOffline):
            return "offline"
        elif isinstance(status, UserStatusRecently):
            return "recently"
        elif isinstance(status, UserStatusLastWeek):
            return "last_week"
        elif isinstance(status, UserStatusLastMonth):
            return "last_month"
        elif isinstance(status, UserStatusEmpty):
            return "long_time_ago"
        return "unknown"

    async def fetch_members(self, channel_id: int, status_dict: Dict[str, Any]) -> Dict[str, int]:
        """Fetch members while holding exclusive access to the session file."""
        async with self.session_lock:
            return await self._fetch_members_locked(channel_id, status_dict)

    async def _fetch_members_locked(self, channel_id: int, status_dict: Dict[str, Any]) -> Dict[str, int]:
        """Fetch all members/participants of a group/channel and save to DB."""
        await self.client.connect()

        if not await self.client.is_user_authorized():
            await self.client.disconnect()
            raise Exception("User not authorized. Please authenticate first.")

        try:
            # Get the entity by ID
            status_dict["message"] = "Resolving channel entity..."
            try:
                entity = await self.client.get_entity(channel_id)
            except ValueError:
                # Try with -100 prefix for supergroups/channels
                try:
                    entity = await self.client.get_entity(int(f"-100{channel_id}"))
                except Exception:
                    raise Exception(f"Could not find channel/group with ID {channel_id}")

            entity_title = getattr(entity, 'title', 'group')
            status_dict["message"] = f"Fetching members of {entity_title}..."

            # Fetch participants — different API for Chat vs Channel/supergroup
            participants = []
            try:
                if isinstance(entity, Chat):
                    # Basic groups use GetFullChatRequest
                    full = await self.client(GetFullChatRequest(entity.id))
                    participants = list(full.users)
                else:
                    # Supergroups and channels use get_participants
                    participants = await self.client.get_participants(entity, limit=None)
            except ChatAdminRequiredError:
                raise Exception("Admin rights required to list members of this group/channel.")

            if not participants:
                # Fallback: try get_participants anyway (works for some Chat types)
                try:
                    fallback = await self.client.get_participants(entity, limit=None)
                    if fallback:
                        participants = fallback
                except Exception:
                    pass

            status_dict["total"] = len(participants)
            status_dict["processed"] = 0

            added = 0
            updated = 0

            for user in participants:
                user_status = self._get_user_status(user.status)

                # Check if member already exists
                existing = await self.db.execute(
                    select(GroupMember).where(
                        GroupMember.channel_id == channel_id,
                        GroupMember.user_id == user.id
                    )
                )
                existing_member = existing.scalar_one_or_none()

                if existing_member:
                    existing_member.first_name = user.first_name
                    existing_member.last_name = user.last_name
                    existing_member.username = user.username
                    existing_member.phone = user.phone
                    existing_member.is_bot = user.bot or False
                    existing_member.is_premium = getattr(user, 'premium', False) or False
                    existing_member.status = user_status
                    existing_member.fetched_at = datetime.utcnow()
                    updated += 1
                else:
                    new_member = GroupMember(
                        channel_id=channel_id,
                        user_id=user.id,
                        first_name=user.first_name,
                        last_name=user.last_name,
                        username=user.username,
                        phone=user.phone,
                        is_bot=user.bot or False,
                        is_premium=getattr(user, 'premium', False) or False,
                        status=user_status,
                    )
                    self.db.add(new_member)
                    added += 1

                status_dict["processed"] += 1

                # Commit in batches
                if (added + updated) % 50 == 0:
                    await self.db.commit()

            await self.db.commit()

            return {
                "members_added": added,
                "members_updated": updated,
                "total": added + updated,
            }

        except FloodWaitError as e:
            await self.db.rollback()
            raise Exception(f"Rate limited by Telegram. Wait {e.seconds} seconds.")
        except ChatAdminRequiredError:
            await self.db.rollback()
            raise Exception("Admin rights required to list members of this group/channel.")
        except RPCError as e:
            await self.db.rollback()
            raise Exception(f"Telegram API error: {e}")
        finally:
            await self.client.disconnect()
