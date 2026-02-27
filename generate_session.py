#!/usr/bin/env python3
"""
Run this ONCE on your local machine (outside Docker) to authenticate
Pyrogram and create the session file. After this you won't need to
enter a code again — the session file handles auth automatically.

Usage:
    source venv/bin/activate   # or: python3 -m venv venv && pip install pyrogram tgcrypto
    python3 generate_session.py
"""

import os
import asyncio
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

API_ID   = int(os.environ["PYROGRAM_API_ID"])
API_HASH = os.environ["PYROGRAM_API_HASH"]
PHONE    = os.environ["PYROGRAM_PHONE"]

# Session file will be saved here as pyrogram_session.session
SESSION_DIR = Path(".").resolve()

async def main():
    try:
        from pyrogram import Client
    except ImportError:
        print("Install pyrogram first:  pip install pyrogram tgcrypto")
        return

    print(f"\nLogging in as {PHONE} ...")
    print("Telegram will send a code to your Telegram app.\n")

    client = Client(
        name="pyrogram_session",
        api_id=API_ID,
        api_hash=API_HASH,
        phone_number=PHONE,
        workdir=str(SESSION_DIR),
    )

    async with client:
        me = await client.get_me()
        print(f"\n✅  Authenticated as: {me.first_name} (@{me.username})")
        print(f"    Session saved → {SESSION_DIR / 'pyrogram_session.session'}")
        print("\nYou can now copy this file into Docker — see instructions below.")

if __name__ == "__main__":
    asyncio.run(main())
