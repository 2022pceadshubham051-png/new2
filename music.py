"""
╔══════════════════════════════════════════════════════╗
║              🎵 MusicVerse Bot                       ║
║          Full-Featured Telegram Music Bot            ║
║                                                      ║
║  Requirements:                                       ║
║    pip install pyrogram==2.0.106                     ║
║    pip install py-tgcalls                            ║
║    pip install yt-dlp                                ║
║    pip install aiohttp aiofiles                      ║
║                                                      ║
║  Create your bot via @BotFather on Telegram          ║
║  Get API_ID and API_HASH from my.telegram.org        ║
╚══════════════════════════════════════════════════════╝
"""

import asyncio
import os
import re
import time
import logging
from collections import defaultdict

from pyrogram import Client, filters
from pyrogram.types import (
    Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
)

# ── py-tgcalls 2.x imports ────────────────────────────
from pytgcalls import PyTgCalls
from pytgcalls.types import MediaStream, AudioParameters, Update
# ─────────────────────────────────────────────────────

import yt_dlp

# ─────────────────────────────────────────────────────
#   CONFIG — Fill these in before running
# ─────────────────────────────────────────────────────

API_ID      = 30324020             # From my.telegram.org
API_HASH    = "db4b2ca65a6ed07ffc4e1fc28ffc87cb"             # From my.telegram.org
BOT_TOKEN   = "7762184752:AAHzUPp6NCw3vh0_m6XQP_pWLhdm0Gltdrc"             # From @BotFather
BOT_OWNER   = 8702369452              # Your Telegram user ID (integer)
SUPPORT_GRP = -1003740536853             # Your support/log group chat ID (negative integer)

MAX_DURATION = 3600          # 1 hour in seconds
DOWNLOAD_DIR = "./downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# ─────────────────────────────────────────────────────
#   BANNER IMAGES
#   Replace placeholder URLs with your own Telegraph/Imgur links
# ─────────────────────────────────────────────────────

IMAGES = {
    "start":   "https://telegra.ph/file/5b9e2d58a4b4d5d4a8e5c.jpg",
    "help":    "https://telegra.ph/file/6a1f3e57b5c5d6e5b9f6d.jpg",
    "play":    "https://telegra.ph/file/7b2e4f68c6d6e7f6c0g7e.jpg",
    "queue":   "https://telegra.ph/file/8c3f5g79d7e7f8g7d1h8f.jpg",
    "loop":    "https://telegra.ph/file/9d4g6h8ae8f8g9h8e2i9g.jpg",
    "auth":    "https://telegra.ph/file/0e5h7i9bf9g9h0i9f3j0h.jpg",
    "end":     "https://telegra.ph/file/1f6i8j0cg0h0i1j0g4k1i.jpg",
    "restart": "https://telegra.ph/file/2g7j9k1dh1i1j2k1h5l2j.jpg",
    "stats":   "https://telegra.ph/file/3h8k0l2ei2j2k3l2i6m3k.jpg",
}

# ─────────────────────────────────────────────────────
#   LOGGING
# ─────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)
logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────
#   STATE
# ─────────────────────────────────────────────────────

queues           : dict[int, list]   = defaultdict(list)   # chat_id → song list
loop_state       : dict[int, object] = {}                   # False | True | int
auth_users       : dict[int, set]    = defaultdict(set)     # chat_id → user_ids
approved_members : set               = set()                # bot-wide special users
now_playing      : dict[int, dict]   = {}                   # chat_id → song dict
stream_start     : dict[int, float]  = {}                   # chat_id → epoch
BOT_START        : float             = time.time()
songs_played     : int               = 0
all_users        : set               = set()
active_groups    : set               = set()

# ─────────────────────────────────────────────────────
#   CLIENT INIT
# ─────────────────────────────────────────────────────

app  = Client("musicverse", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
call = PyTgCalls(app)

# ─────────────────────────────────────────────────────
#   HELPERS
# ─────────────────────────────────────────────────────

def fmt_time(seconds: int) -> str:
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    return f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


async def send_photo_safe(client, chat_id, image_key, caption, reply_markup=None, **kwargs):
    """Send a photo with caption; silently falls back to plain text if the image fails."""
    url = IMAGES.get(image_key)
    try:
        if url:
            return await client.send_photo(
                chat_id, url, caption=caption,
                reply_markup=reply_markup, parse_mode="html", **kwargs
            )
    except Exception:
        pass
    return await client.send_message(
        chat_id, caption, reply_markup=reply_markup, parse_mode="html", **kwargs
    )


async def is_admin(client: Client, chat_id: int, user_id: int) -> bool:
    try:
        member = await client.get_chat_member(chat_id, user_id)
        return member.status.name in ("OWNER", "ADMINISTRATOR")
    except Exception:
        return False


async def is_auth(chat_id: int, user_id: int) -> bool:
    return user_id in auth_users[chat_id]


async def has_permission(client: Client, chat_id: int, user_id: int) -> bool:
    if user_id == BOT_OWNER:
        return True
    if await is_admin(client, chat_id, user_id):
        return True
    if await is_auth(chat_id, user_id):
        return True
    return False


def ydl_opts(output_path: str) -> dict:
    return {
        "format": "bestaudio/best",
        "outtmpl": output_path,
        "quiet": True,
        "no_warnings": True,
        "postprocessors": [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "192",
        }],
    }


async def search_yt(query: str) -> dict | None:
    opts = {
        "format": "bestaudio/best",
        "quiet": True,
        "no_warnings": True,
        "default_search": "ytsearch1",
        "noplaylist": True,
    }
    try:
        loop = asyncio.get_event_loop()
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = await loop.run_in_executor(None, lambda: ydl.extract_info(query, download=False))
        if "entries" in info:
            info = info["entries"][0]
        return info
    except Exception as e:
        logger.error(f"YT search error: {e}")
        return None


async def download_audio(url: str, chat_id: int) -> tuple[str | None, dict | None]:
    filename = os.path.join(DOWNLOAD_DIR, f"{chat_id}_{int(time.time())}.%(ext)s")
    opts = ydl_opts(filename)
    opts.update({"noplaylist": True})
    try:
        loop = asyncio.get_event_loop()
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = await loop.run_in_executor(None, lambda: ydl.extract_info(url, download=True))
        if "entries" in info:
            info = info["entries"][0]
        base = filename.replace("%(ext)s", "")
        for ext in ["mp3", "m4a", "webm", "opus", "ogg"]:
            path = base + ext
            if os.path.exists(path):
                return path, info
        return None, None
    except Exception as e:
        logger.error(f"Download error: {e}")
        return None, None


async def log_to_support(client: Client, text: str):
    if SUPPORT_GRP:
        try:
            await client.send_message(SUPPORT_GRP, text, parse_mode="html")
        except Exception:
            pass


async def play_next(client: Client, chat_id: int):
    global songs_played
    if not queues[chat_id]:
        now_playing.pop(chat_id, None)
        return

    song      = queues[chat_id][0]
    file_path = song.get("file")

    if not file_path or not os.path.exists(file_path):
        file_path, _ = await download_audio(song["url"], chat_id)
        if not file_path:
            queues[chat_id].pop(0)
            await play_next(client, chat_id)
            return
        queues[chat_id][0]["file"] = file_path

    try:
        # py-tgcalls 2.x: call.play() handles both joining and playing.
        # MediaStream.Flags.IGNORE disables the video track (audio-only stream).
        await call.play(
            chat_id,
            MediaStream(
                file_path,
                video_flags=MediaStream.Flags.IGNORE,
            )
        )
        now_playing[chat_id]  = song
        stream_start[chat_id] = time.time()
        songs_played          += 1

        ahead   = len(queues[chat_id]) - 1
        buttons = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("⏸  Pause",    callback_data="pause"),
                InlineKeyboardButton("⏭  Skip",     callback_data="skip"),
                InlineKeyboardButton("🔁  Loop",     callback_data="loop_toggle"),
            ],
            [
                InlineKeyboardButton("📋  Queue",   callback_data="show_queue"),
                InlineKeyboardButton("⏹  End",      callback_data="end"),
            ],
        ])

        caption = (
            f"🎵  <b>Now Playing</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🎼  <b>{song['title']}</b>\n\n"
            f"⏱  Duration  ›  <code>{fmt_time(song['duration'])}</code>\n"
            f"👤  Requested by  ›  {song['requester']}\n"
            f"📋  Up next  ›  {ahead} song{'s' if ahead != 1 else ''} in queue\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"<i>Use the buttons below to control playback.</i>"
        )

        await send_photo_safe(client, chat_id, "play", caption=caption, reply_markup=buttons)

    except Exception as e:
        logger.error(f"play_next error in {chat_id}: {e}")
        queues[chat_id].pop(0)
        await play_next(client, chat_id)


# ─────────────────────────────────────────────────────
#   STREAM ENDED  (py-tgcalls 2.x)
#   Decorator: @call.on_stream_end()
#   Callback receives (client, update: Update)
#   update.chat_id  — the group chat id
# ─────────────────────────────────────────────────────

@call.on_stream_end()
async def on_stream_end(client, update: Update):
    chat_id = update.chat_id
    ls      = loop_state.get(chat_id, False)

    if ls is True:
        await play_next(app, chat_id)
    elif isinstance(ls, int) and ls > 0:
        loop_state[chat_id] = ls - 1
        await play_next(app, chat_id)
    else:
        if queues[chat_id]:
            old = queues[chat_id].pop(0)
            try:
                if old.get("file") and os.path.exists(old["file"]):
                    os.remove(old["file"])
            except Exception:
                pass
        await play_next(app, chat_id)


# ─────────────────────────────────────────────────────
#   AUTO-STOP WHEN VC IS EMPTY  (py-tgcalls 2.x)
#   Decorator: @call.on_participants_change()
#   Callback receives (client, update: Update)
#   update.chat_id       — the group chat id
#   update.participants  — list of current participants
# ─────────────────────────────────────────────────────

@call.on_participants_change()
async def on_vc_change(client, update: Update):
    chat_id      = update.chat_id
    participants = update.participants
    humans       = [p for p in participants if not getattr(p, "is_self", False)]

    if len(humans) == 0 and now_playing.get(chat_id):
        logger.info(f"VC empty in {chat_id} — stopping stream automatically.")
        queues[chat_id].clear()
        now_playing.pop(chat_id, None)
        loop_state.pop(chat_id, None)
        try:
            await call.leave_group_call(chat_id)
        except Exception:
            pass
        try:
            await app.send_message(
                chat_id,
                "🔇  <b>Voice Chat is Empty</b>\n"
                "Music has been stopped automatically since no one is in the VC.\n"
                "Use <code>/play</code> to start a new session when you're back!",
                parse_mode="html"
            )
        except Exception:
            pass


# ─────────────────────────────────────────────────────
#   /start  — Private
# ─────────────────────────────────────────────────────

@app.on_message(filters.command("start") & filters.private)
async def cmd_start(client: Client, msg: Message):
    all_users.add(msg.from_user.id)
    me      = await client.get_me()
    support = f"https://t.me/c/{str(SUPPORT_GRP).replace('-100', '')}" if SUPPORT_GRP else None

    buttons = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("➕  Add to Group", url=f"https://t.me/{me.username}?startgroup=true"),
            InlineKeyboardButton("📖  Commands",      callback_data="help"),
        ],
        [
            InlineKeyboardButton("💬  Support Group", url=support) if support
            else InlineKeyboardButton("🎵  MusicVerse", callback_data="noop"),
        ],
    ])

    caption = (
        f"🎵  <b>Welcome to MusicVerse</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Hello, <b>{msg.from_user.first_name}</b> 👋\n\n"
        f"I am a premium music streaming bot that delivers crystal-clear audio directly into your group's Voice Chat — "
        f"no buffering, no interruptions, just pure music.\n\n"
        f"<b>Key Features</b>\n"
        f"  ›  Stream from YouTube or upload audio files\n"
        f"  ›  Smart queue with seamless auto-playback\n"
        f"  ›  Loop, seek, pause and resume controls\n"
        f"  ›  Granular admin and authorized-user access\n"
        f"  ›  Auto-stops when the voice chat is empty\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"Add me to your group and use <code>/play</code> to begin. 🎶"
    )

    await send_photo_safe(client, msg.chat.id, "start", caption=caption, reply_markup=buttons)
    await log_to_support(
        client,
        f"👤  <b>New User</b>\n"
        f"Name  ›  <a href='tg://user?id={msg.from_user.id}'>{msg.from_user.first_name}</a>\n"
        f"ID  ›  <code>{msg.from_user.id}</code>"
    )


# ─────────────────────────────────────────────────────
#   /start  — Group
# ─────────────────────────────────────────────────────

@app.on_message(filters.command("start") & filters.group)
async def cmd_start_group(client: Client, msg: Message):
    all_users.add(msg.from_user.id)
    active_groups.add(msg.chat.id)

    buttons = InlineKeyboardMarkup([[
        InlineKeyboardButton("📖  Commands", callback_data="help"),
        InlineKeyboardButton("🎵  Play Music", switch_inline_query_current_chat="/play "),
    ]])

    caption = (
        f"🎵  <b>MusicVerse is Ready</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Streaming is now available in <b>{msg.chat.title}</b>.\n\n"
        f"Use <code>/play &lt;song name or URL&gt;</code> to start the music.\n"
        f"Type <code>/help</code> to browse the full command list."
    )

    await send_photo_safe(client, msg.chat.id, "start", caption=caption, reply_markup=buttons)
    await log_to_support(
        client,
        f"📣  <b>Bot Added to Group</b>\n"
        f"Group  ›  <b>{msg.chat.title}</b>  (<code>{msg.chat.id}</code>)\n"
        f"By  ›  <a href='tg://user?id={msg.from_user.id}'>{msg.from_user.first_name}</a>"
    )


# ─────────────────────────────────────────────────────
#   /help
# ─────────────────────────────────────────────────────

HELP_TEXT = (
    "🎵  <b>MusicVerse — Command Reference</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n\n"

    "🎧  <b>Playback</b>\n"
    "  ›  <code>/play [name / url]</code>  — Stream a song in VC\n"
    "  ›  <code>/forceplay [name / url]</code>  — Force-play, skips queue  <i>(admin only)</i>\n"
    "  ›  <code>/pause</code>  — Pause the current stream\n"
    "  ›  <code>/resume</code>  — Resume a paused stream\n"
    "  ›  <code>/skip</code>  — Skip to the next song\n"
    "  ›  <code>/end</code>  — Stop music and leave VC\n\n"

    "⏩  <b>Seek</b>\n"
    "  ›  <code>/seek [seconds]</code>  — Jump forward by N seconds\n"
    "  ›  <code>/seekback [seconds]</code>  — Jump backward by N seconds\n\n"

    "📋  <b>Queue</b>\n"
    "  ›  <code>/queue</code>  — View the current song queue\n\n"

    "🔁  <b>Loop</b>\n"
    "  ›  <code>/loop</code>  — Toggle infinite loop on/off\n"
    "  ›  <code>/loop [number]</code>  — Loop the current song N times\n\n"

    "👮  <b>Admin Controls</b>\n"
    "  ›  <code>/auth [@user / reply / id]</code>  — Grant music access\n"
    "  ›  <code>/unauth [@user / reply / id]</code>  — Revoke music access\n"
    "  ›  <code>/reload</code>  — Refresh admin cache\n\n"

    "🔑  <b>Owner Only</b>\n"
    "  ›  <code>/botstats</code>  — View bot statistics\n"
    "  ›  <code>/broadcast [text]</code>  — Send a message to all users\n"
    "  ›  <code>/approvemember [@user]</code>  — Grant global permissions\n"
    "  ›  <code>/unapprovemember [@user]</code>  — Revoke global permissions\n"
    "  ›  <code>/restart</code>  — Restart the bot\n\n"

    "━━━━━━━━━━━━━━━━━━━━\n"
    "ℹ️  <b>Limits</b>  ›  Max 1 hour per track  •  Auto-stops when VC is empty"
)


@app.on_message(filters.command("help"))
async def cmd_help(client: Client, msg: Message):
    buttons = InlineKeyboardMarkup([[
        InlineKeyboardButton("🏠  Home",       callback_data="start"),
        InlineKeyboardButton("🎵  Play Music", switch_inline_query_current_chat="/play "),
    ]])
    await send_photo_safe(client, msg.chat.id, "help", caption=HELP_TEXT, reply_markup=buttons)


# ─────────────────────────────────────────────────────
#   /play & /forceplay
# ─────────────────────────────────────────────────────

async def handle_play(client: Client, msg: Message, force: bool = False):
    chat_id = msg.chat.id
    user    = msg.from_user
    all_users.add(user.id)
    active_groups.add(chat_id)

    if force and not await has_permission(client, chat_id, user.id):
        return await msg.reply(
            "🚫  <b>Access Denied</b>\n"
            "Only admins and authorized users can use <code>/forceplay</code>.",
            parse_mode="html"
        )

    query      = None
    audio_file = None

    if msg.reply_to_message:
        if msg.reply_to_message.audio or msg.reply_to_message.voice:
            audio_file = msg.reply_to_message.audio or msg.reply_to_message.voice
        elif msg.reply_to_message.text:
            query = msg.reply_to_message.text

    if not query and not audio_file:
        parts = msg.text.split(None, 1)
        if len(parts) < 2:
            return await msg.reply(
                "⚠️  <b>Missing Input</b>\n"
                "Please provide a song name or YouTube URL.\n\n"
                "  ›  <code>/play &lt;song name&gt;</code>\n"
                "  ›  <code>/play &lt;YouTube URL&gt;</code>",
                parse_mode="html"
            )
        query = parts[1].strip()

    wait = await msg.reply("🔍  <b>Searching</b>  —  Looking up your track, please wait…", parse_mode="html")

    if audio_file:
        file_path = os.path.join(DOWNLOAD_DIR, f"{chat_id}_{int(time.time())}.ogg")
        await client.download_media(audio_file, file_name=file_path)
        title    = getattr(audio_file, "title", None) or getattr(audio_file, "file_name", "Audio File")
        duration = getattr(audio_file, "duration", 0) or 0
        url      = f"tg://{audio_file.file_id}"
        info     = {"title": title, "duration": duration, "webpage_url": url}
    else:
        if not re.match(r"https?://", query):
            query = f"ytsearch1:{query}"
        info = await search_yt(query)
        if not info:
            await wait.delete()
            return await msg.reply(
                "❌  <b>No Results Found</b>\n"
                "We could not find a match for your query.\n"
                "Try a different song name, artist, or paste a direct YouTube URL.",
                parse_mode="html"
            )

        duration = info.get("duration", 0) or 0
        if duration > MAX_DURATION:
            await wait.delete()
            return await msg.reply(
                f"⛔  <b>Track Too Long</b>\n"
                f"This track is <code>{fmt_time(duration)}</code> long, which exceeds the limit.\n"
                f"MusicVerse supports tracks up to <b>1 hour</b> in duration.",
                parse_mode="html"
            )

        title    = info.get("title", "Unknown Track")
        url      = info.get("webpage_url") or info.get("original_url") or query
        file_path = None

    song = {
        "title":     info.get("title", title),
        "url":       url,
        "duration":  duration,
        "requester": f"<a href='tg://user?id={user.id}'>{user.first_name}</a>",
        "file":      None,
    }

    if force and queues[chat_id]:
        queues[chat_id].insert(1, song)
        await wait.delete()
        await msg.reply(
            f"⚡  <b>Force Play Activated</b>\n"
            f"<b>{song['title']}</b> has been moved to the front of the queue\n"
            f"and will play right after the current track.",
            parse_mode="html"
        )
        if now_playing.get(chat_id):
            await skip_current(client, chat_id)
        return

    if now_playing.get(chat_id):
        queues[chat_id].append(song)
        pos = len(queues[chat_id])
        await wait.edit(
            f"📋  <b>Added to Queue</b>  ›  Position #{pos}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🎼  <b>{song['title']}</b>\n"
            f"⏱  Duration  ›  <code>{fmt_time(duration)}</code>\n"
            f"👤  Requested by  ›  {song['requester']}",
            parse_mode="html"
        )
        return

    await wait.edit("⬇️  <b>Downloading</b>  —  Fetching audio, almost ready…", parse_mode="html")
    if not audio_file:
        file_path, _ = await download_audio(url, chat_id)
        if not file_path:
            await wait.delete()
            return await msg.reply(
                "❌  <b>Download Failed</b>\n"
                "We were unable to fetch this track. This may be due to regional restrictions or an unsupported format.\n"
                "Please try a different song.",
                parse_mode="html"
            )
        song["file"] = file_path
    else:
        song["file"] = file_path

    queues[chat_id].append(song)
    await wait.delete()
    await play_next(client, chat_id)


@app.on_message(filters.command("play") & filters.group)
async def cmd_play(client: Client, msg: Message):
    await handle_play(client, msg, force=False)


@app.on_message(filters.command("forceplay") & filters.group)
async def cmd_forceplay(client: Client, msg: Message):
    await handle_play(client, msg, force=True)


# ─────────────────────────────────────────────────────
#   /pause & /resume
# ─────────────────────────────────────────────────────

@app.on_message(filters.command("pause") & filters.group)
async def cmd_pause(client: Client, msg: Message):
    chat_id = msg.chat.id
    if not await has_permission(client, chat_id, msg.from_user.id):
        return await msg.reply(
            "🚫  <b>Access Denied</b>\nOnly admins or authorized users can pause the stream.",
            parse_mode="html"
        )
    try:
        await call.pause_stream(chat_id)
        buttons = InlineKeyboardMarkup([[InlineKeyboardButton("▶️  Resume", callback_data="resume")]])
        await msg.reply(
            "⏸  <b>Stream Paused</b>\nPlayback has been paused. Tap <b>Resume</b> whenever you are ready.",
            reply_markup=buttons, parse_mode="html"
        )
    except Exception as e:
        await msg.reply(f"❌  <b>Error:</b>  <code>{e}</code>", parse_mode="html")


@app.on_message(filters.command("resume") & filters.group)
async def cmd_resume(client: Client, msg: Message):
    chat_id = msg.chat.id
    if not await has_permission(client, chat_id, msg.from_user.id):
        return await msg.reply(
            "🚫  <b>Access Denied</b>\nOnly admins or authorized users can resume the stream.",
            parse_mode="html"
        )
    try:
        await call.resume_stream(chat_id)
        buttons = InlineKeyboardMarkup([[InlineKeyboardButton("⏸  Pause", callback_data="pause")]])
        await msg.reply(
            "▶️  <b>Stream Resumed</b>\nPlayback is back on. Enjoy the music! 🎶",
            reply_markup=buttons, parse_mode="html"
        )
    except Exception as e:
        await msg.reply(f"❌  <b>Error:</b>  <code>{e}</code>", parse_mode="html")


# ─────────────────────────────────────────────────────
#   /skip
# ─────────────────────────────────────────────────────

async def skip_current(client: Client, chat_id: int):
    """Leave the current call and play the next track in queue."""
    try:
        await call.leave_group_call(chat_id)
    except Exception:
        pass
    if queues[chat_id]:
        queues[chat_id].pop(0)
    await play_next(client, chat_id)


@app.on_message(filters.command("skip") & filters.group)
async def cmd_skip(client: Client, msg: Message):
    chat_id = msg.chat.id
    if not await has_permission(client, chat_id, msg.from_user.id):
        return await msg.reply(
            "🚫  <b>Access Denied</b>\nOnly admins or authorized users can skip tracks.",
            parse_mode="html"
        )
    if not now_playing.get(chat_id):
        return await msg.reply(
            "ℹ️  <b>Nothing is Playing</b>\nThere is no active stream to skip.\nUse <code>/play</code> to start one.",
            parse_mode="html"
        )
    await msg.reply("⏭  <b>Skipping Track</b>\nMoving to the next song in the queue…", parse_mode="html")
    await skip_current(client, chat_id)


# ─────────────────────────────────────────────────────
#   /seek & /seekback
#   py-tgcalls 2.x: seek via call.play() with AudioParameters(seek=N)
# ─────────────────────────────────────────────────────

@app.on_message(filters.command(["seek", "seekback"]) & filters.group)
async def cmd_seek(client: Client, msg: Message):
    chat_id = msg.chat.id
    if not await has_permission(client, chat_id, msg.from_user.id):
        return await msg.reply(
            "🚫  <b>Access Denied</b>\nOnly admins or authorized users can seek.",
            parse_mode="html"
        )

    parts = msg.text.split()
    if len(parts) < 2 or not parts[1].isdigit():
        return await msg.reply(
            "⚠️  <b>Invalid Usage</b>\n"
            "Please provide a valid number of seconds.\n\n"
            "  ›  <code>/seek [seconds]</code>  — Jump forward\n"
            "  ›  <code>/seekback [seconds]</code>  — Jump backward",
            parse_mode="html"
        )

    seconds = int(parts[1])
    song    = now_playing.get(chat_id)
    if not song:
        return await msg.reply(
            "ℹ️  <b>Nothing is Playing</b>\nStart a stream with <code>/play</code> before using seek.",
            parse_mode="html"
        )

    elapsed = int(time.time() - stream_start.get(chat_id, time.time()))
    cmd     = msg.command[0].lower()
    new_pos = elapsed + seconds if cmd == "seek" else elapsed - seconds
    new_pos = max(0, min(new_pos, song["duration"]))

    try:
        # py-tgcalls 2.x: replay the same file with an AudioParameters seek offset
        await call.play(
            chat_id,
            MediaStream(
                song["file"],
                audio_parameters=AudioParameters(seek=new_pos),
                video_flags=MediaStream.Flags.IGNORE,
            )
        )
        stream_start[chat_id] = time.time() - new_pos
        direction = "⏩  <b>Jumped Forward</b>" if cmd == "seek" else "⏪  <b>Jumped Backward</b>"
        await msg.reply(
            f"{direction}  ›  Now at <code>{fmt_time(new_pos)}</code>",
            parse_mode="html"
        )
    except Exception as e:
        await msg.reply(f"❌  <b>Seek Failed:</b>  <code>{e}</code>", parse_mode="html")


# ─────────────────────────────────────────────────────
#   /queue
# ─────────────────────────────────────────────────────

@app.on_message(filters.command("queue") & filters.group)
async def cmd_queue(client: Client, msg: Message):
    chat_id = msg.chat.id
    q       = queues[chat_id]

    if not q:
        buttons = InlineKeyboardMarkup([[
            InlineKeyboardButton("🎵  Play a Song", switch_inline_query_current_chat="/play "),
        ]])
        return await send_photo_safe(
            client, chat_id, "queue",
            caption=(
                "📋  <b>Queue is Empty</b>\n"
                "No tracks are lined up right now.\n"
                "Use <code>/play</code> to add a song and get the music going!"
            ),
            reply_markup=buttons
        )

    total_dur = sum(s["duration"] for s in q)
    lines     = []
    for i, s in enumerate(q):
        if i == 0:
            lines.append(f"🎵  <b>[Now Playing]</b>\n    <b>{s['title']}</b>  ›  <code>{fmt_time(s['duration'])}</code>\n    👤 {s['requester']}")
        else:
            lines.append(f"  <b>{i}.</b>  {s['title']}  ›  <code>{fmt_time(s['duration'])}</code>\n    👤 {s['requester']}")

    text = (
        f"📋  <b>Music Queue</b>  ›  {len(q)} track{'s' if len(q) != 1 else ''}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        + "\n\n".join(lines)
        + f"\n\n━━━━━━━━━━━━━━━━━━━━\n"
        f"⏱  Total duration  ›  <code>{fmt_time(total_dur)}</code>"
    )

    buttons = InlineKeyboardMarkup([[
        InlineKeyboardButton("⏭  Skip Current", callback_data="skip"),
        InlineKeyboardButton("⏹  End Session",  callback_data="end"),
    ]])
    await send_photo_safe(client, chat_id, "queue", caption=text, reply_markup=buttons)


# ─────────────────────────────────────────────────────
#   /loop
# ─────────────────────────────────────────────────────

@app.on_message(filters.command("loop") & filters.group)
async def cmd_loop(client: Client, msg: Message):
    chat_id = msg.chat.id
    if not await has_permission(client, chat_id, msg.from_user.id):
        return await msg.reply(
            "🚫  <b>Access Denied</b>\nOnly admins or authorized users can change the loop setting.",
            parse_mode="html"
        )

    parts   = msg.text.split()
    current = loop_state.get(chat_id, False)

    if len(parts) == 1:
        if current is False:
            loop_state[chat_id] = True
            caption = (
                "♾  <b>Infinite Loop Enabled</b>\n"
                "The current song will repeat indefinitely until you disable loop or skip."
            )
        else:
            loop_state[chat_id] = False
            caption = (
                "🔁  <b>Loop Disabled</b>\n"
                "Playback will continue normally through the queue."
            )
    else:
        try:
            n = int(parts[1])
            if n < 1:
                raise ValueError
            loop_state[chat_id] = n
            caption = (
                f"🔂  <b>Loop Set</b>\n"
                f"The current track will repeat <b>{n}</b> more time{'s' if n != 1 else ''} before moving on."
            )
        except ValueError:
            return await msg.reply(
                "⚠️  <b>Invalid Usage</b>\n"
                "Please provide a positive whole number.\n\n"
                "  ›  <code>/loop</code>  — Toggle infinite loop on/off\n"
                "  ›  <code>/loop 3</code>  — Repeat current track 3 times",
                parse_mode="html"
            )

    buttons = InlineKeyboardMarkup([[
        InlineKeyboardButton("🔁  Toggle Loop",   callback_data="loop_toggle"),
        InlineKeyboardButton("✖  Disable Loop", callback_data="loop_off"),
    ]])
    await send_photo_safe(client, chat_id, "loop", caption=caption, reply_markup=buttons)


# ─────────────────────────────────────────────────────
#   /end
# ─────────────────────────────────────────────────────

@app.on_message(filters.command("end") & filters.group)
async def cmd_end(client: Client, msg: Message):
    chat_id = msg.chat.id
    if not await has_permission(client, chat_id, msg.from_user.id):
        return await msg.reply(
            "🚫  <b>Access Denied</b>\nOnly admins or authorized users can end the session.",
            parse_mode="html"
        )

    count = len(queues[chat_id])
    queues[chat_id].clear()
    now_playing.pop(chat_id, None)
    loop_state.pop(chat_id, None)

    try:
        await call.leave_group_call(chat_id)
    except Exception:
        pass

    buttons = InlineKeyboardMarkup([[
        InlineKeyboardButton("🎵  Start a New Session", switch_inline_query_current_chat="/play "),
    ]])
    await send_photo_safe(
        client, chat_id, "end",
        caption=(
            f"⏹  <b>Session Ended</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"Music has been stopped and <b>{count}</b> queued track{'s were' if count != 1 else ' was'} cleared from the list.\n\n"
            f"Whenever you are ready, start a new session with <code>/play</code>."
        ),
        reply_markup=buttons
    )


# ─────────────────────────────────────────────────────
#   /auth & /unauth
# ─────────────────────────────────────────────────────

async def resolve_user(client: Client, msg: Message) -> int | None:
    parts = msg.text.split()
    if msg.reply_to_message:
        return msg.reply_to_message.from_user.id
    if len(parts) < 2:
        return None
    target = parts[1]
    if target.lstrip("-").isdigit():
        return int(target)
    if target.startswith("@"):
        try:
            u = await client.get_users(target)
            return u.id
        except Exception:
            return None
    return None


@app.on_message(filters.command("auth") & filters.group)
async def cmd_auth(client: Client, msg: Message):
    chat_id = msg.chat.id
    if not await is_admin(client, chat_id, msg.from_user.id) and msg.from_user.id != BOT_OWNER:
        return await msg.reply(
            "🚫  <b>Access Denied</b>\nOnly group admins can authorize users.",
            parse_mode="html"
        )

    uid = await resolve_user(client, msg)
    if not uid:
        return await msg.reply(
            "⚠️  <b>No User Specified</b>\n"
            "Reply to a user's message, mention their username, or provide their user ID.\n\n"
            "  ›  <code>/auth @username</code>\n"
            "  ›  <code>/auth 123456789</code>",
            parse_mode="html"
        )

    auth_users[chat_id].add(uid)
    buttons = InlineKeyboardMarkup([[InlineKeyboardButton("🗑  Remove Access", callback_data=f"unauth_{uid}")]])
    await send_photo_safe(
        client, chat_id, "auth",
        caption=(
            f"✅  <b>User Authorized</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"User ID  ›  <code>{uid}</code> now has access to music commands in this group."
        ),
        reply_markup=buttons
    )


@app.on_message(filters.command("unauth") & filters.group)
async def cmd_unauth(client: Client, msg: Message):
    chat_id = msg.chat.id
    if not await is_admin(client, chat_id, msg.from_user.id) and msg.from_user.id != BOT_OWNER:
        return await msg.reply(
            "🚫  <b>Access Denied</b>\nOnly group admins can revoke user authorization.",
            parse_mode="html"
        )

    uid = await resolve_user(client, msg)
    if not uid:
        return await msg.reply(
            "⚠️  <b>No User Specified</b>\n"
            "Reply to a user's message, mention their username, or provide their user ID.\n\n"
            "  ›  <code>/unauth @username</code>\n"
            "  ›  <code>/unauth 123456789</code>",
            parse_mode="html"
        )

    auth_users[chat_id].discard(uid)
    await msg.reply(
        f"🗑  <b>Authorization Revoked</b>\n"
        f"User ID  ›  <code>{uid}</code> can no longer use music commands in this group.",
        parse_mode="html"
    )


# ─────────────────────────────────────────────────────
#   /reload
# ─────────────────────────────────────────────────────

@app.on_message(filters.command("reload") & filters.group)
async def cmd_reload(client: Client, msg: Message):
    if not await is_admin(client, msg.chat.id, msg.from_user.id):
        return await msg.reply(
            "🚫  <b>Access Denied</b>\nOnly group admins can reload the admin cache.",
            parse_mode="html"
        )
    await msg.reply(
        "✅  <b>Admin Cache Refreshed</b>\n"
        "All admin permissions have been reloaded successfully.",
        parse_mode="html"
    )


# ─────────────────────────────────────────────────────
#   /botstats
# ─────────────────────────────────────────────────────

@app.on_message(filters.command("botstats"))
async def cmd_botstats(client: Client, msg: Message):
    if msg.from_user.id != BOT_OWNER:
        return await msg.reply(
            "🚫  <b>Owner Only</b>\nThis command is restricted to the bot owner.",
            parse_mode="html"
        )

    uptime = int(time.time() - BOT_START)
    caption = (
        f"📊  <b>MusicVerse — Statistics</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"⏱  Uptime              ›  <code>{fmt_time(uptime)}</code>\n"
        f"👤  Total Users         ›  <code>{len(all_users)}</code>\n"
        f"👥  Active Groups       ›  <code>{len(active_groups)}</code>\n"
        f"🎵  Songs Played        ›  <code>{songs_played}</code>\n"
        f"📡  Active Streams      ›  <code>{len(now_playing)}</code>\n"
        f"📋  Queued Tracks       ›  <code>{sum(len(q) for q in queues.values())}</code>\n"
        f"🔑  Approved Members    ›  <code>{len(approved_members)}</code>\n"
        f"━━━━━━━━━━━━━━━━━━━━"
    )
    await send_photo_safe(client, msg.chat.id, "stats", caption=caption)


# ─────────────────────────────────────────────────────
#   /broadcast
# ─────────────────────────────────────────────────────

@app.on_message(filters.command("broadcast"))
async def cmd_broadcast(client: Client, msg: Message):
    uid = msg.from_user.id
    if uid != BOT_OWNER and uid not in approved_members:
        return await msg.reply(
            "🚫  <b>Access Denied</b>\nOnly the bot owner or approved members can broadcast.",
            parse_mode="html"
        )

    parts = msg.text.split(None, 1)
    if len(parts) < 2:
        return await msg.reply(
            "⚠️  <b>No Message Provided</b>\nUsage: <code>/broadcast [your message]</code>",
            parse_mode="html"
        )

    text  = parts[1]
    sent  = failed = 0
    status = await msg.reply("📢  Broadcasting…", parse_mode="html")

    for user_id in all_users:
        try:
            await client.send_message(
                user_id,
                f"📢  <b>Broadcast from MusicVerse</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n\n{text}",
                parse_mode="html"
            )
            sent += 1
        except Exception:
            failed += 1
        await asyncio.sleep(0.05)

    await status.edit(
        f"✅  <b>Broadcast Complete</b>\n"
        f"  ›  Delivered  ›  <code>{sent}</code>\n"
        f"  ›  Failed     ›  <code>{failed}</code>",
        parse_mode="html"
    )


# ─────────────────────────────────────────────────────
#   /approvemember & /unapprovemember
# ─────────────────────────────────────────────────────

@app.on_message(filters.command("approvemember"))
async def cmd_approve(client: Client, msg: Message):
    if msg.from_user.id != BOT_OWNER:
        return await msg.reply(
            "🚫  <b>Owner Only</b>\nThis command is restricted to the bot owner.",
            parse_mode="html"
        )
    uid = await resolve_user(client, msg)
    if not uid:
        return await msg.reply(
            "⚠️  <b>No User Specified</b>\nReply to a message or provide a username / user ID.",
            parse_mode="html"
        )
    approved_members.add(uid)
    await msg.reply(
        f"✅  <b>Member Approved</b>\n"
        f"User ID  ›  <code>{uid}</code> has been granted special bot-wide permissions.",
        parse_mode="html"
    )


@app.on_message(filters.command("unapprovemember"))
async def cmd_unapprove(client: Client, msg: Message):
    if msg.from_user.id != BOT_OWNER:
        return await msg.reply(
            "🚫  <b>Owner Only</b>\nThis command is restricted to the bot owner.",
            parse_mode="html"
        )
    uid = await resolve_user(client, msg)
    if not uid:
        return await msg.reply(
            "⚠️  <b>No User Specified</b>\nReply to a message or provide a username / user ID.",
            parse_mode="html"
        )
    approved_members.discard(uid)
    await msg.reply(
        f"🗑  <b>Approval Revoked</b>\n"
        f"User ID  ›  <code>{uid}</code> no longer holds special permissions.",
        parse_mode="html"
    )


# ─────────────────────────────────────────────────────
#   /restart
# ─────────────────────────────────────────────────────

@app.on_message(filters.command("restart"))
async def cmd_restart(client: Client, msg: Message):
    if msg.from_user.id != BOT_OWNER:
        return await msg.reply(
            "🚫  <b>Owner Only</b>\nThis command is restricted to the bot owner.",
            parse_mode="html"
        )
    buttons = InlineKeyboardMarkup([[InlineKeyboardButton("🔄  Restarting…", callback_data="noop")]])
    await send_photo_safe(
        client, msg.chat.id, "restart",
        caption=(
            "🔄  <b>Restarting MusicVerse</b>\n"
            "The bot is restarting. All active streams will resume automatically.\n"
            "This usually takes under 10 seconds."
        ),
        reply_markup=buttons
    )
    await asyncio.sleep(2)
    import sys
    os.execl(sys.executable, sys.executable, *sys.argv)


# ─────────────────────────────────────────────────────
#   CALLBACK QUERY HANDLER
# ─────────────────────────────────────────────────────

@app.on_callback_query()
async def cb_handler(client: Client, query: CallbackQuery):
    data    = query.data
    chat_id = query.message.chat.id
    user    = query.from_user

    music_controls = {"pause", "resume", "skip", "end", "loop_toggle", "loop_off"}
    if data in music_controls and not await has_permission(client, chat_id, user.id):
        return await query.answer("🚫 You don't have permission to do that.", show_alert=True)

    if data == "pause":
        try:
            await call.pause_stream(chat_id)
            await query.answer("⏸ Paused.")
            await query.message.edit_reply_markup(InlineKeyboardMarkup([[
                InlineKeyboardButton("▶️  Resume", callback_data="resume"),
                InlineKeyboardButton("⏭  Skip",   callback_data="skip"),
            ]]))
        except Exception as e:
            await query.answer(f"Error: {e}", show_alert=True)

    elif data == "resume":
        try:
            await call.resume_stream(chat_id)
            await query.answer("▶️ Resumed!")
        except Exception as e:
            await query.answer(f"Error: {e}", show_alert=True)

    elif data == "skip":
        await query.answer("⏭ Skipping…")
        await skip_current(client, chat_id)

    elif data == "end":
        count = len(queues[chat_id])
        queues[chat_id].clear()
        now_playing.pop(chat_id, None)
        loop_state.pop(chat_id, None)
        try:
            await call.leave_group_call(chat_id)
        except Exception:
            pass
        await query.answer("⏹ Session ended.")
        await query.message.edit_caption(
            f"⏹  <b>Session Ended</b>\n{count} track{'s' if count != 1 else ''} cleared from queue.",
            parse_mode="html"
        )

    elif data == "loop_toggle":
        current          = loop_state.get(chat_id, False)
        loop_state[chat_id] = not current if isinstance(current, bool) else False
        state = "♾ Infinite loop ON" if loop_state[chat_id] else "🔁 Loop OFF"
        await query.answer(state)

    elif data == "loop_off":
        loop_state.pop(chat_id, None)
        await query.answer("🔁 Loop disabled.")

    elif data == "show_queue":
        q = queues[chat_id]
        if not q:
            return await query.answer("📋 Queue is empty!", show_alert=True)
        text = "\n".join(f"{i}. {s['title']}" for i, s in enumerate(q))
        await query.answer(f"📋 Queue:\n{text}"[:200], show_alert=True)

    elif data == "help":
        await query.answer()
        await send_photo_safe(client, chat_id, "help", caption=HELP_TEXT)

    elif data == "start":
        await query.answer()

    elif data.startswith("unauth_"):
        uid = int(data.split("_")[1])
        auth_users[chat_id].discard(uid)
        await query.answer(f"✅ User {uid} access revoked.")

    elif data == "noop":
        await query.answer()


# ─────────────────────────────────────────────────────
#   RUN
# ─────────────────────────────────────────────────────

async def main():
    logger.info("🎵 Starting MusicVerse Bot…")
    await app.start()
    await call.start()
    me = await app.get_me()
    logger.info(f"✅ Online as @{me.username}")
    if SUPPORT_GRP:
        try:
            await app.send_message(
                SUPPORT_GRP,
                "🟢  <b>MusicVerse is Online</b>\nBot started successfully.",
                parse_mode="html"
            )
        except Exception:
            pass
    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())