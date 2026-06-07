import os

# ── Telegram API Credentials ──────────────────────────────────────────────────
API_ID = int(os.getenv("API_ID", "30324020"))
API_HASH = os.getenv("API_HASH", "db4b2ca65a6ed07ffc4e1fc28ffc87cb")
BOT_TOKEN = os.getenv("BOT_TOKEN", "7762184752:AAGBMkyoE8XG7sFWKqYyjCKpMyOAbR-udro")

# ── Pyrogram String Session (for Voice Chat user) ─────────────────────────────
SESSION_STRING = os.getenv(
    "SESSION_STRING",
    "AQHOtTQAXTdB5aMYZCDqWzxJjebNzqOPIuK20PSbyuXeUXV9hhs0oVlJvdDLEFrL1_56w-EEq1qxxzYDyrhkmc2o7yUhqIIHRr1FkK7L_IojQfK2TS1jOHMMWdg7AekS6YVQjntZfCZ0YkLUbJUfPhgad2TTZL_pD_z-02NXggQHvNTVfAkIo4D1MEbg_3xQKW-Kkfm_6tdY9b-uO6r1appmnO5OB_fRhmfUGQwz5GTtxUfRGxRXWBcf94C5nTNHMIZ-fco_LJqB1Qqsizg25ZqrcRr5I5FaEgyC7rlMIjCxCIPrf7bBH3c-GgAdQd4hZh_7yTBscE7NOdecAYQAf52D0I3FiAAAAAIGs56sAA",
)

# ── Owner & Support ───────────────────────────────────────────────────────────
OWNER_ID = int(os.getenv("OWNER_ID", "8702369452"))

# ── Support Group (gets join/new user notifications) ─────────────────────────
# Set this to your support group chat_id (negative number for groups)
SUPPORT_GROUP_ID = int(os.getenv("SUPPORT_GROUP_ID", "0"))

# ── Limits ────────────────────────────────────────────────────────────────────
MAX_DURATION_SECONDS = 3600  # 1 hour max song duration
MAX_QUEUE_SIZE = 50  # Max songs in queue per chat
IDLE_TIMEOUT_SECONDS = 300  # Auto-leave if VC empty for 5 minutes
