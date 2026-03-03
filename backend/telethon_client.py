"""Telegram client for ingesting channels into database."""

import os
import asyncio
from typing import Dict, Any
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from telethon import TelegramClient
from telethon.tl.types import Channel, Chat
from telethon.errors import FloodWaitError, RPCError

from models import Channel as ChannelModel


class TelegramIngestion:
    """Handles ingestion of Telegram channels into the database."""
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self.api_id = int(os.getenv('TELEGRAM_API_ID'))
        self.api_hash = os.getenv('TELEGRAM_API_HASH')
        self.session_name = os.getenv('SESSION_NAME', 'list_channels_session')
        self.client = TelegramClient(self.session_name, self.api_id, self.api_hash)
    
    async def run_ingestion(self, status_dict: Dict[str, Any]) -> Dict[str, int]:
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
            
            for dialog in channel_dialogs:
                entity = dialog.entity
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
                
                status_dict["processed"] += 1
                
                # Commit every 10 channels to avoid large transactions
                if (added + updated) % 10 == 0:
                    await self.db.commit()
                
                # Small delay to avoid rate limits
                await asyncio.sleep(0.2)
            
            # Final commit
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
