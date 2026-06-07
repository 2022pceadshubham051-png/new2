import os

# ── Telegram API Credentials ──────────────────────────────────────────────────
API_ID = os.getenv("API_ID", "23275523")
API_HASH = os.getenv("API_HASH", "5f470dfdbebf920fe36b6bb4e8cc9053")
BOT_TOKEN = os.getenv("BOT_TOKEN", "7762184752:AAGBMkyoE8XG7sFWKqYyjCKpMyOAbR-udro")

# ── Pyrogram String Session (for Voice Chat user) ─────────────────────────────
SESSION_STRING = os.getenv("BQFjKAMAwLysZzN7oImPsnXD-l3nrMBmjP62eVzIY3mfkcxi5ENlebVJWhBuaAykSrlm0EH96VJElpHsxRikQk6h_4WYIq8EbRBBnQPITCXD8UCxaK-t08saxgQ35DSdQJNqOLOhr8BfgMXBKP4Equb7L0tXntCfGEBV0Wo8_2ZLAIkjJorAZkighIjKLXg4Wujzmo4nYcBh5DXJ5uR6cHILi_gBypUdDaT1Dq6t85T7JVGATrbMHNgAutJJu1LUTrIRIi6tNQiItE2cMreKsoFLZ752EtR-6moxVcyn8xeWml02BQVKOgSD3vWP_AzwXxrfJZQMQOsUOBYb8CHgNTUDSDucjgAAAAIGVRagAA", "")

# ── Owner & Support ───────────────────────────────────────────────────────────
OWNER_ID = int(os.getenv("OWNER_ID", "8000127916"))

# ── Support Group (gets join/new user notifications) ─────────────────────────
# Set this to your support group chat_id (negative number for groups)
SUPPORT_GROUP_ID = int(os.getenv("SUPPORT_GROUP_ID", "0"))

# ── Limits ────────────────────────────────────────────────────────────────────
MAX_DURATION_SECONDS = 3600   # 1 hour max song duration
MAX_QUEUE_SIZE = 50           # Max songs in queue per chat
IDLE_TIMEOUT_SECONDS = 300    # Auto-leave if VC empty for 5 minutes
