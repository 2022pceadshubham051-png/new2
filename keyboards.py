"""
keyboards.py — All InlineKeyboardMarkup builders + themed banner URLs for MusicVerse
"""
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# ── Themed Banner Images ──────────────────────────────────────────────────────
# Using Telegram-hostable image links. Replace with your own Telegraph URLs.
BANNERS = {
    "start":   "https://te.legra.ph/file/a1b6a32a8e99c6e8e83a8.jpg",
    "help":    "https://te.legra.ph/file/a1b6a32a8e99c6e8e83a8.jpg",
    "play":    "https://te.legra.ph/file/a1b6a32a8e99c6e8e83a8.jpg",
    "queue":   "https://te.legra.ph/file/a1b6a32a8e99c6e8e83a8.jpg",
    "loop":    "https://te.legra.ph/file/a1b6a32a8e99c6e8e83a8.jpg",
    "end":     "https://te.legra.ph/file/a1b6a32a8e99c6e8e83a8.jpg",
    "restart": "https://te.legra.ph/file/a1b6a32a8e99c6e8e83a8.jpg",
    "auth":    "https://te.legra.ph/file/a1b6a32a8e99c6e8e83a8.jpg",
    "stats":   "https://te.legra.ph/file/a1b6a32a8e99c6e8e83a8.jpg",
}
# fallback if any key missing
DEFAULT_BANNER = "https://te.legra.ph/file/a1b6a32a8e99c6e8e83a8.jpg"

def get_banner(key: str) -> str:
    return BANNERS.get(key, DEFAULT_BANNER)


# ── Player Controls ───────────────────────────────────────────────────────────
def player_markup() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("⏮ Prev",   callback_data="prev"),
            InlineKeyboardButton("⏸ Pause",  callback_data="pause"),
            InlineKeyboardButton("⏭ Skip",   callback_data="skip"),
        ],
        [
            InlineKeyboardButton("🔁 Loop",   callback_data="loop_toggle"),
            InlineKeyboardButton("▶️ Resume", callback_data="resume"),
            InlineKeyboardButton("⏹ Stop",   callback_data="stop"),
        ],
        [
            InlineKeyboardButton("📋 Queue",  callback_data="queue_view"),
            InlineKeyboardButton("❌ Close",  callback_data="close"),
        ],
    ])


# ── Start Menu ────────────────────────────────────────────────────────────────
def start_markup() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🎵 Commands",  callback_data="cb_help"),
            InlineKeyboardButton("📊 Stats",     callback_data="cb_stats"),
        ],
        [
            InlineKeyboardButton("➕ Add to Group", url="https://t.me/YourBotUsername?startgroup=true"),
            InlineKeyboardButton("💬 Support",      url="https://t.me/YourSupportGroup"),
        ],
    ])


# ── Help Sub-menus ────────────────────────────────────────────────────────────
def help_markup() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🎶 Music",  callback_data="help_music"),
            InlineKeyboardButton("👮 Admin",  callback_data="help_admin"),
        ],
        [
            InlineKeyboardButton("👑 Owner",  callback_data="help_owner"),
            InlineKeyboardButton("🔙 Back",   callback_data="cb_start"),
        ],
    ])


# ── Loop Options ──────────────────────────────────────────────────────────────
def loop_markup(current: int | str) -> InlineKeyboardMarkup:
    """current = 0 (off), 1 (on), or N (N times)"""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🔁 Loop Once",     callback_data="loop_1"),
            InlineKeyboardButton("🔁 Loop 5×",       callback_data="loop_5"),
            InlineKeyboardButton("🔁 Loop 10×",      callback_data="loop_10"),
        ],
        [
            InlineKeyboardButton("♾ Loop Infinite",  callback_data="loop_inf"),
            InlineKeyboardButton("❌ Disable Loop",  callback_data="loop_0"),
        ],
        [InlineKeyboardButton("🔙 Back", callback_data="close")],
    ])


# ── Auth management ───────────────────────────────────────────────────────────
def auth_markup() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Auth User",   callback_data="auth_do"),
            InlineKeyboardButton("❌ Unauth User", callback_data="unauth_do"),
        ],
        [InlineKeyboardButton("📋 List Auth", callback_data="auth_list")],
    ])
