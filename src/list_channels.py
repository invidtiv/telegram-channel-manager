#!/usr/bin/env python3
"""
Telegram Channel Lister

Uses MTProto protocol (via Telethon) to list all channels the account is in.
Handles rate limiting with exponential backoff and automatic retry.

Output: channels_<timestamp>.json and channels_<timestamp>.csv
"""

import os
import sys
import json
import csv
import asyncio
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any
from dataclasses import dataclass, asdict

from dotenv import load_dotenv
from telethon import TelegramClient
from telethon.tl.types import Channel, Chat, User
from telethon.errors import FloodWaitError, RPCError
from telethon.helpers import TotalList

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(f"channel_list_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")
    ]
)
logger = logging.getLogger(__name__)


@dataclass
class ChannelInfo:
    """Represents a Telegram channel/chat."""
    id: int
    bot_chat_id: str  # ID formatted for bot API (-100... for channels/supergroups)
    name: str
    username: str | None
    type: str  # 'channel', 'group', 'supergroup', 'private'
    participants_count: int | None
    is_verified: bool
    is_megagroup: bool
    created_at: str | None
    about: str | None


class RateLimiter:
    """Handles rate limiting with exponential backoff."""
    
    def __init__(self, base_delay: float = 1.0, max_delay: float = 60.0):
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.current_delay = base_delay
        self.consecutive_errors = 0
    
    async def handle_flood_wait(self, seconds: int):
        """Handle Telegram's FloodWaitError."""
        wait_time = min(seconds + 5, 300)  # Add 5s buffer, cap at 5 min
        logger.warning(f"FloodWaitError: Waiting {wait_time} seconds...")
        await asyncio.sleep(wait_time)
        self.consecutive_errors += 1
    
    async def backoff(self):
        """Exponential backoff for general errors."""
        delay = min(self.current_delay * (2 ** self.consecutive_errors), self.max_delay)
        logger.warning(f"Backing off for {delay} seconds...")
        await asyncio.sleep(delay)
        self.consecutive_errors += 1
    
    def reset(self):
        """Reset backoff on success."""
        if self.consecutive_errors > 0:
            logger.info("Rate limit cleared, resuming normal operations")
        self.consecutive_errors = 0
        self.current_delay = self.base_delay


class TelegramChannelLister:
    """Lists all channels using MTProto with rate limiting."""
    
    def __init__(self, api_id: int, api_hash: str, session_name: str = "list_channels_session"):
        self.client = TelegramClient(session_name, api_id, api_hash)
        self.rate_limiter = RateLimiter(base_delay=0.5, max_delay=60.0)
        self.channels: List[ChannelInfo] = []
    
    async def __aenter__(self):
        logger.info("Connecting to Telegram...")
        await self.client.connect()
        
        if not await self.client.is_user_authorized():
            logger.error("User not authorized! Please run the script interactively first to authenticate.")
            phone = os.getenv('TELEGRAM_PHONE')
            if not phone:
                logger.error("TELEGRAM_PHONE not set in environment variables")
                raise ValueError("Phone number required for first-time authentication")
            
            await self.client.send_code_request(phone)
            code = input("Enter the code you received: ")
            await self.client.sign_in(phone, code)
        
        logger.info("Successfully connected!")
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.client.disconnect()
        logger.info("Disconnected from Telegram")
    
    async def get_dialogs_with_retry(self) -> TotalList:
        """Fetch dialogs with rate limit handling."""
        max_retries = 5
        
        for attempt in range(max_retries):
            try:
                # Get all dialogs (conversations) - this includes channels, groups, and private chats
                logger.info("Fetching dialogs...")
                dialogs = await self.client.get_dialogs(limit=None)
                self.rate_limiter.reset()
                return dialogs
            except FloodWaitError as e:
                await self.rate_limiter.handle_flood_wait(e.seconds)
            except RPCError as e:
                logger.error(f"RPC Error: {e}")
                if attempt < max_retries - 1:
                    await self.rate_limiter.backoff()
                else:
                    raise
            except Exception as e:
                logger.error(f"Unexpected error: {e}")
                if attempt < max_retries - 1:
                    await self.rate_limiter.backoff()
                else:
                    raise
        
        raise RuntimeError("Max retries exceeded for get_dialogs")
    
    async def get_channel_info_with_retry(self, entity) -> ChannelInfo | None:
        """Get detailed channel info with rate limit handling."""
        max_retries = 3
        
        for attempt in range(max_retries):
            try:
                # Small delay between requests to avoid hitting limits
                await asyncio.sleep(0.3)
                
                # Get full channel info
                full_entity = await self.client.get_entity(entity)
                
                # Determine channel type
                if isinstance(full_entity, Channel):
                    if full_entity.megagroup:
                        channel_type = "supergroup"
                    else:
                        channel_type = "channel"
                elif isinstance(full_entity, Chat):
                    channel_type = "group"
                elif isinstance(full_entity, User):
                    channel_type = "private"
                else:
                    channel_type = "unknown"
                
                # Try to get participant count (may fail for private channels)
                participants_count = None
                try:
                    if hasattr(full_entity, 'participants_count'):
                        participants_count = full_entity.participants_count
                except Exception:
                    pass
                
                # Calculate bot chat ID format
                # For supergroups and channels: -100{id}
                # For regular groups: -{id}
                # For private chats: {id} (positive)
                if channel_type in ('channel', 'supergroup'):
                    bot_chat_id = f"-100{full_entity.id}"
                elif channel_type == 'group':
                    bot_chat_id = f"-{full_entity.id}"
                else:
                    bot_chat_id = str(full_entity.id)
                
                info = ChannelInfo(
                    id=full_entity.id,
                    bot_chat_id=bot_chat_id,
                    name=getattr(full_entity, 'title', None) or 
                         getattr(full_entity, 'first_name', '') + ' ' + getattr(full_entity, 'last_name', ''),
                    username=getattr(full_entity, 'username', None),
                    type=channel_type,
                    participants_count=participants_count,
                    is_verified=getattr(full_entity, 'verified', False),
                    is_megagroup=getattr(full_entity, 'megagroup', False),
                    created_at=datetime.now().isoformat(),
                    about=None  # Would require additional API call, skipping for rate limit safety
                )
                
                self.rate_limiter.reset()
                return info
                
            except FloodWaitError as e:
                await self.rate_limiter.handle_flood_wait(e.seconds)
            except Exception as e:
                logger.warning(f"Error getting info for entity {entity}: {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(1)
                else:
                    return None
        
        return None
    
    async def list_all_channels(self) -> List[ChannelInfo]:
        """Main method to list all channels."""
        dialogs = await self.get_dialogs_with_retry()
        
        logger.info(f"Found {len(dialogs)} dialogs total")
        
        # Filter to only channels, supergroups, and groups (not private chats with users)
        channel_dialogs = [
            d for d in dialogs 
            if isinstance(d.entity, (Channel, Chat)) and not (
                isinstance(d.entity, Channel) and not d.entity.megagroup and d.entity.participants_count is None
            )
        ]
        
        logger.info(f"Processing {len(channel_dialogs)} channels/groups...")
        
        for i, dialog in enumerate(channel_dialogs, 1):
            logger.info(f"[{i}/{len(channel_dialogs)}] Processing: {dialog.name}")
            
            info = await self.get_channel_info_with_retry(dialog.entity)
            if info:
                self.channels.append(info)
                logger.info(f"  ✓ ID: {info.id}, Type: {info.type}")
            else:
                # Fallback to basic dialog info
                # Try to determine bot_chat_id from dialog info
                entity = dialog.entity
                if hasattr(entity, 'megagroup') and entity.megagroup:
                    bot_chat_id = f"-100{entity.id}"
                elif isinstance(entity, Channel):
                    bot_chat_id = f"-100{entity.id}"
                elif isinstance(entity, Chat):
                    bot_chat_id = f"-{entity.id}"
                else:
                    bot_chat_id = str(entity.id)
                
                self.channels.append(ChannelInfo(
                    id=entity.id,
                    bot_chat_id=bot_chat_id,
                    name=dialog.name or "Unknown",
                    username=None,
                    type="unknown",
                    participants_count=None,
                    is_verified=False,
                    is_megagroup=False,
                    created_at=None,
                    about=None
                ))
        
        logger.info(f"Successfully processed {len(self.channels)} channels")
        return self.channels
    
    def save_results(self, output_dir: str = "output"):
        """Save results to JSON and CSV."""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_path = Path(output_dir)
        output_path.mkdir(exist_ok=True)
        
        # Save as JSON
        json_file = output_path / f"channels_{timestamp}.json"
        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump([asdict(c) for c in self.channels], f, indent=2, ensure_ascii=False)
        logger.info(f"Saved JSON: {json_file}")
        
        # Save as CSV
        csv_file = output_path / f"channels_{timestamp}.csv"
        with open(csv_file, 'w', newline='', encoding='utf-8') as f:
            if self.channels:
                writer = csv.DictWriter(f, fieldnames=asdict(self.channels[0]).keys())
                writer.writeheader()
                writer.writerows([asdict(c) for c in self.channels])
        logger.info(f"Saved CSV: {csv_file}")
        
        # Also save a simple text list for easy reading
        txt_file = output_path / f"channels_{timestamp}.txt"
        with open(txt_file, 'w', encoding='utf-8') as f:
            f.write(f"Telegram Channels List - Generated {datetime.now().isoformat()}\n")
            f.write("=" * 80 + "\n\n")
            for c in self.channels:
                f.write(f"ID: {c.id}\n")
                f.write(f"Bot Chat ID: {c.bot_chat_id}\n")
                f.write(f"Name: {c.name}\n")
                f.write(f"Username: @{c.username}\n" if c.username else "Username: (none)\n")
                f.write(f"Type: {c.type}\n")
                f.write(f"Members: {c.participants_count or 'N/A'}\n")
                f.write("-" * 40 + "\n")
        logger.info(f"Saved TXT: {txt_file}")
        
        return json_file, csv_file, txt_file


def load_config() -> Dict[str, Any]:
    """Load configuration from environment variables."""
    # Load .env file if it exists
    env_path = Path(__file__).parent.parent / "config" / ".env"
    if env_path.exists():
        load_dotenv(env_path)
    
    api_id = os.getenv('TELEGRAM_API_ID')
    api_hash = os.getenv('TELEGRAM_API_HASH')
    phone = os.getenv('TELEGRAM_PHONE')
    session_name = os.getenv('SESSION_NAME', 'list_channels_session')
    
    if not api_id or not api_hash:
        logger.error("Missing TELEGRAM_API_ID or TELEGRAM_API_HASH")
        logger.error("Please set these in config/.env or as environment variables")
        logger.error("Get your credentials from: https://my.telegram.org/apps")
        sys.exit(1)
    
    try:
        api_id = int(api_id)
    except ValueError:
        logger.error("TELEGRAM_API_ID must be a number")
        sys.exit(1)
    
    return {
        'api_id': api_id,
        'api_hash': api_hash,
        'phone': phone,
        'session_name': session_name
    }


async def main():
    """Main entry point."""
    print("=" * 80)
    print("Telegram Channel Lister")
    print("Uses MTProto to list all channels your account is in")
    print("=" * 80)
    print()
    
    config = load_config()
    
    logger.info(f"Session name: {config['session_name']}")
    logger.info("Starting channel listing process...")
    
    async with TelegramChannelLister(
        api_id=config['api_id'],
        api_hash=config['api_hash'],
        session_name=config['session_name']
    ) as lister:
        channels = await lister.list_all_channels()
        
        if channels:
            json_file, csv_file, txt_file = lister.save_results()
            print()
            print("=" * 80)
            print("✓ Channel listing complete!")
            print(f"  Total channels found: {len(channels)}")
            print()
            print("Output files:")
            print(f"  JSON: {json_file}")
            print(f"  CSV:  {csv_file}")
            print(f"  TXT:  {txt_file}")
            print("=" * 80)
        else:
            logger.warning("No channels found or an error occurred")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        sys.exit(0)
    except Exception as e:
        logger.exception("Fatal error")
        sys.exit(1)
