#!/usr/bin/env python3
"""Helper script to authenticate with Telegram (one-time setup)."""

import os
import sys
import asyncio

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load environment variables
from pathlib import Path
env_file = Path(__file__).parent.parent / "config" / ".env"
if env_file.exists():
    with open(env_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                os.environ.setdefault(key, value)

from telethon import TelegramClient

API_ID = os.getenv('TELEGRAM_API_ID')
API_HASH = os.getenv('TELEGRAM_API_HASH')
SESSION_NAME = os.getenv('SESSION_NAME', 'list_channels_session')

async def authenticate():
    """Run one-time authentication."""
    if not API_ID or not API_HASH:
        print("❌ Error: TELEGRAM_API_ID and TELEGRAM_API_HASH must be set in config/.env")
        print("\nGet them from: https://my.telegram.org/apps")
        return

    print("🔐 Telegram Authentication")
    print("=" * 50)
    print(f"API ID: {API_ID}")
    print(f"Session: {SESSION_NAME}")
    print("=" * 50)
    print()

    session_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), SESSION_NAME)
    client = TelegramClient(session_path, int(API_ID), API_HASH)
    await client.connect()

    if await client.is_user_authorized():
        print("✅ Already authenticated!")
        me = await client.get_me()
        print(f"   Logged in as: {me.first_name} (@{me.username or 'no_username'})")
    else:
        print("📱 Not authenticated. Starting login flow...")
        print()
        
        phone = input("Enter your phone number (with country code, e.g. +1234567890): ").strip()
        
        try:
            await client.send_code_request(phone)
            print("📤 Verification code sent to your Telegram app!")
            print()
            
            code = input("Enter the code you received: ").strip()
            await client.sign_in(phone, code)
            
            print()
            print("✅ Authentication successful!")
            me = await client.get_me()
            print(f"   Logged in as: {me.first_name} (@{me.username or 'no_username'})")
            
        except Exception as e:
            print(f"❌ Error: {e}")
            return

    await client.disconnect()
    print()
    print("💾 Session saved. You can now use the web app!")
    print(f"   Session file: {SESSION_NAME}.session")

if __name__ == "__main__":
    asyncio.run(authenticate())
