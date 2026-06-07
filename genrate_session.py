"""
genrate_session.py — Generate a Pyrogram string session for MusicVerse
Run: python genrate_session.py
"""
import asyncio
try:
    loop = asyncio.get_event_loop()
except RuntimeError:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

from pyrogram import Client

API_ID   = input("Enter your API_ID: ").strip()
API_HASH = input("Enter your API_HASH: ").strip()

async def main():
    print("\n📲 Enter your phone number when prompted (with country code, e.g. +918485886358)")
    app = Client("session_gen", api_id=API_ID, api_hash=API_HASH, in_memory=True)
    await app.start()
    string = await app.export_session_string()
    print("\n" + "=" * 60)
    print("✅  YOUR SESSION STRING IS:")
    print("=" * 60)
    print(string)
    print("=" * 60)
    print("\n📋 Copy the string above and set it as SESSION_STRING in config.py\n")
    await app.stop()

asyncio.run(main())
