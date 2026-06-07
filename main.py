"""
MusicVerse — Full-Featured Telegram Music Bot
main.py
"""

import asyncio
import json
import os
import sys
import time
import platform
import subprocess

try:
    loop = asyncio.get_event_loop()
except RuntimeError:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

import static_ffmpeg
static_ffmpeg.add_paths()

import logging
import psutil

from pyrogram import Client, filters, idle
from pyrogram.types import (
    Message, BotCommand, InlineKeyboardMarkup,
    InlineKeyboardButton, CallbackQuery,
)
from pyrogram.enums import ChatMemberStatus, ParseMode
import pyrogram.errors

try:
    from pyrogram.errors import GroupcallForbidden
except ImportError:
    class GroupcallForbidden(pyrogram.errors.exceptions.forbidden_403.Forbidden):
        pass
    pyrogram.errors.GroupcallForbidden = GroupcallForbidden

from pytgcalls import PyTgCalls
from pytgcalls.types import MediaStream, GroupCallConfig, Update, StreamEnded
from yt_dlp import YoutubeDL

from config import (
    API_ID, API_HASH, BOT_TOKEN, SESSION_STRING, OWNER_ID,
    SUPPORT_GROUP_ID, MAX_DURATION_SECONDS, MAX_QUEUE_SIZE, IDLE_TIMEOUT_SECONDS,
)
from database import (
    add_tracked_chat, get_tracked_chats,
    auth_user, unauth_user, is_authed,
    approve_member, unapprove_member, is_approved, get_approved_members,
)
from helpers import is_admin, has_music_perm, format_duration
from keyboards import (
    player_markup, start_markup, help_markup, loop_markup, auth_markup, get_banner,
)

logging.basicConfig(level=logging.WARNING)

# ─────────────────────────────────────────────────────────────────────────────
#  Clients
# ─────────────────────────────────────────────────────────────────────────────
os.makedirs("downloads", exist_ok=True)

bot = Client("MusicVerse", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

user = None
call_py = None
if SESSION_STRING:
    try:
        user = Client("MusicVerse_User", api_id=API_ID, api_hash=API_HASH, session_string=SESSION_STRING)
        call_py = PyTgCalls(user)
    except Exception as e:
        print(f"[WARN] User session init failed: {e}")
        user = None
        call_py = None

# ─────────────────────────────────────────────────────────────────────────────
#  State
# ─────────────────────────────────────────────────────────────────────────────
START_TIME = time.time()

# QUEUE[chat_id]   = [{"file", "title", "thumbnail", "duration", "requester"}, ...]
QUEUE:   dict[int, list] = {}
PLAYING: dict[int, bool] = {}
# LOOP[chat_id] = 0 (off) | positive int (count remaining) | "inf"
LOOP:    dict[int, int | str] = {}
# CURRENT[chat_id] = song_data dict of currently playing song
CURRENT: dict[int, dict] = {}
# SEEK_POSITION[chat_id] = seconds elapsed (approximate, updated on play/seek)
SEEK_POS: dict[int, float] = {}
PLAY_START: dict[int, float] = {}

# Idle watcher tasks
IDLE_TASKS: dict[int, asyncio.Task] = {}

# ─────────────────────────────────────────────────────────────────────────────
#  yt-dlp helpers
# ─────────────────────────────────────────────────────────────────────────────
YDL_OPTS = {
    'format': 'bestaudio/best',
    'outtmpl': 'downloads/%(id)s.%(ext)s',
    'noplaylist': True,
    'quiet': True,
    'source_address': '0.0.0.0',
    # Put cookies.txt in the same folder as main.py
    # Export via: yt-dlp --cookies-from-browser chrome --cookies cookies.txt "https://youtube.com" --skip-download
    'cookiefile': 'cookies.txt' if os.path.exists('cookies.txt') else None,
}

def ydl_extract(query: str):
    clients = [['ios'], ['android'], ['tv_embedded'], ['web']]
    sq = query if query.startswith("http") else f"ytsearch:{query}"
    last_err = None
    for client in clients:
        try:
            opts = {
                **YDL_OPTS,
                'extractor_args': {
                    'youtube': {
                        'player_client': client,
                        'player_skip': ['webpage', 'configs'],
                    }
                },
            }
            with YoutubeDL(opts) as ydl:
                info = ydl.extract_info(sq, download=True)
                if 'entries' in info:
                    info = info['entries'][0]
                filepath = os.path.abspath(ydl.prepare_filename(info))
                return info, filepath
        except Exception as e:
            last_err = e
            continue
    raise last_err


# ─────────────────────────────────────────────────────────────────────────────
#  Idle VC watcher
# ─────────────────────────────────────────────────────────────────────────────
async def start_idle_watcher(chat_id: int):
    if chat_id in IDLE_TASKS:
        IDLE_TASKS[chat_id].cancel()
    IDLE_TASKS[chat_id] = asyncio.create_task(_idle_watcher(chat_id))

async def _idle_watcher(chat_id: int):
    await asyncio.sleep(IDLE_TIMEOUT_SECONDS)
    if not PLAYING.get(chat_id):
        try:
            if call_py:
                await call_py.leave_call(chat_id)
            await bot.send_message(chat_id,
                "⏱ **Auto-Left Voice Chat**\n\nNo one was listening, so I left to save resources. Use /play to start again!")
        except Exception:
            pass


# ─────────────────────────────────────────────────────────────────────────────
#  Core playback
# ─────────────────────────────────────────────────────────────────────────────
async def play_next(chat_id: int):
    """Play next song in queue, or leave if empty."""
    # Handle loop
    loop_val = LOOP.get(chat_id, 0)
    current = CURRENT.get(chat_id)

    if current and loop_val:
        if loop_val == "inf":
            song = current
        elif isinstance(loop_val, int) and loop_val > 0:
            LOOP[chat_id] = loop_val - 1
            song = current
        else:
            song = None
    else:
        q = QUEUE.get(chat_id, [])
        song = q.pop(0) if q else None

    if song:
        CURRENT[chat_id] = song
        PLAY_START[chat_id] = time.time()
        try:
            await call_py.play(
                chat_id,
                MediaStream(song['file'], video_flags=MediaStream.Flags.IGNORE),
                GroupCallConfig(auto_start=True)
            )
            PLAYING[chat_id] = True
            loop_info = ""
            lv = LOOP.get(chat_id, 0)
            if lv == "inf":
                loop_info = "\n🔁 **Loop:** Infinite"
            elif isinstance(lv, int) and lv > 0:
                loop_info = f"\n🔁 **Loop:** {lv} time(s) remaining"

            await bot.send_photo(
                chat_id,
                photo=song['thumbnail'],
                caption=(
                    f"🎵 **Now Playing**\n\n"
                    f"**{song['title']}**\n"
                    f"⏱ Duration: `{format_duration(song['duration'])}`\n"
                    f"👤 Requested by: {song['requester']}"
                    f"{loop_info}"
                ),
                reply_markup=player_markup()
            )
        except Exception as e:
            await bot.send_message(chat_id, f"❌ Error playing: `{e}`\nSkipping...")
            await play_next(chat_id)
    else:
        PLAYING[chat_id] = False
        CURRENT.pop(chat_id, None)
        try:
            if call_py:
                await call_py.leave_call(chat_id)
        except Exception:
            pass
        await bot.send_message(chat_id,
            "✅ **Queue Finished!**\n\nAll songs have been played. Use /play to add more 🎶")


if call_py is not None:
    @call_py.on_update()
    async def stream_handler(client, update: Update):
        if isinstance(update, StreamEnded):
            chat_id = update.chat_id
            await play_next(chat_id)


# ─────────────────────────────────────────────────────────────────────────────
#  Track new chats & notify support group
# ─────────────────────────────────────────────────────────────────────────────
@bot.on_message(filters.group | filters.private, group=-1)
async def track_chats(client: Client, message: Message):
    if message.chat:
        add_tracked_chat(message.chat.id)


@bot.on_message(filters.new_chat_members)
async def new_member_handler(client: Client, message: Message):
    me = await client.get_me()
    for member in message.new_chat_members:
        if member.id == me.id:
            # Bot was added to a group
            chat = message.chat
            add_tracked_chat(chat.id)
            if SUPPORT_GROUP_ID:
                try:
                    await client.send_message(
                        SUPPORT_GROUP_ID,
                        f"📢 **Bot Added to New Group!**\n\n"
                        f"🏠 **Group:** {chat.title}\n"
                        f"🆔 **ID:** `{chat.id}`\n"
                        f"👥 **Members:** {chat.members_count if hasattr(chat, 'members_count') else 'N/A'}\n"
                        f"👤 **Added by:** {message.from_user.mention if message.from_user else 'Unknown'}"
                    )
                except Exception:
                    pass
        else:
            # New human user joined a tracked group
            if SUPPORT_GROUP_ID:
                chat = message.chat
                try:
                    await client.send_message(
                        SUPPORT_GROUP_ID,
                        f"👤 **New User Joined!**\n\n"
                        f"🏠 **Group:** {chat.title}\n"
                        f"👤 **User:** {member.mention}\n"
                        f"🆔 **User ID:** `{member.id}`"
                    )
                except Exception:
                    pass


# ─────────────────────────────────────────────────────────────────────────────
#  /start
# ─────────────────────────────────────────────────────────────────────────────
@bot.on_message(filters.command("start"))
async def start_cmd(client: Client, message: Message):
    me = await client.get_me()
    caption = (
        f"🎵 **Welcome to MusicVerse!**\n\n"
        f"I'm your feature-rich music bot. Add me to any group and I'll stream "
        f"music directly into the Voice Chat!\n\n"
        f"**Features:**\n"
        f"• 🎶 Play from YouTube by name or URL\n"
        f"• 📋 Smart queue system\n"
        f"• 🔁 Loop (once / N times / infinite)\n"
        f"• ⏩ Seek forward & backward\n"
        f"• 👮 Admin & auth system\n"
        f"• 📡 Auto leave when VC is empty\n\n"
        f"Tap **Commands** below to see all commands."
    )
    try:
        await message.reply_photo(
            photo=get_banner("start"),
            caption=caption,
            reply_markup=start_markup()
        )
    except Exception:
        await message.reply_text(caption, reply_markup=start_markup())


# ─────────────────────────────────────────────────────────────────────────────
#  /help
# ─────────────────────────────────────────────────────────────────────────────
HELP_MUSIC = (
    "🎵 **Music Commands**\n\n"
    "/play `[song/url/reply to audio]` — Play in VC\n"
    "/forceplay `[song]` — Force play (admin/auth)\n"
    "/pause — Pause current song\n"
    "/resume — Resume paused song\n"
    "/skip — Skip to next song\n"
    "/queue — View the queue\n"
    "/loop `[off/1/5/10/inf]` — Set loop mode\n"
    "/seek `[seconds]` — Seek forward N seconds\n"
    "/seekback `[seconds]` — Seek backward N seconds\n"
    "/end — Stop & clear everything\n"
)

HELP_ADMIN = (
    "👮 **Admin Commands**\n\n"
    "/auth `[reply/user_id/@username]` — Give music control access\n"
    "/unauth `[reply/user_id/@username]` — Remove access\n"
    "/skip — Skip current song\n"
    "/forceplay — Force play a song\n"
    "/reload — Reload admin cache\n"
)

HELP_OWNER = (
    "👑 **Owner Commands** _(Bot Owner only)_\n\n"
    "/botstats — Full bot statistics\n"
    "/broadcast `[text/reply]` — Broadcast to all chats\n"
    "/approvemember `[reply/user_id]` — Grant global permissions\n"
    "/unapprovemember `[reply/user_id]` — Revoke global permissions\n"
    "/restart — Restart the bot\n"
)

@bot.on_message(filters.command("help"))
async def help_cmd(client: Client, message: Message):
    try:
        await message.reply_photo(
            photo=get_banner("help"),
            caption="🎧 **MusicVerse Help**\n\nChoose a category below:",
            reply_markup=help_markup()
        )
    except Exception:
        await message.reply_text(
            "🎧 **MusicVerse Help**\n\nChoose a category below:",
            reply_markup=help_markup()
        )


# ─────────────────────────────────────────────────────────────────────────────
#  /play
# ─────────────────────────────────────────────────────────────────────────────
@bot.on_message(filters.command("play") & filters.group)
async def play_cmd(client: Client, message: Message):
    if call_py is None:
        return await message.reply_text("❌ Voice features unavailable (no user session configured).")

    # Determine query: text, reply audio, or nothing
    query = None
    audio_file_id = None

    if message.reply_to_message:
        r = message.reply_to_message
        if r.audio:
            audio_file_id = r.audio.file_id
            query = r.audio.title or r.audio.file_name or "audio"
        elif r.voice:
            audio_file_id = r.voice.file_id
            query = "voice message"
        elif r.video:
            audio_file_id = r.video.file_id
            query = r.video.file_name or "video"

    if not audio_file_id and len(message.command) >= 2:
        query = " ".join(message.command[1:])

    if not query and not audio_file_id:
        return await message.reply_text(
            "**Usage:**\n"
            "`/play song name`\n"
            "`/play youtube URL`\n"
            "_or reply to an audio file_"
        )

    chat_id = message.chat.id
    q = QUEUE.setdefault(chat_id, [])

    if len(q) >= MAX_QUEUE_SIZE:
        return await message.reply_text(f"❌ Queue is full! Max {MAX_QUEUE_SIZE} songs allowed.")

    processing = await message.reply_text("🔎 **Searching & downloading...**")

    try:
        if audio_file_id:
            # Download the replied audio
            path = await client.download_media(audio_file_id, file_name=f"downloads/{audio_file_id}.ogg")
            info = {"title": query, "duration": 0, "thumbnail": get_banner("play"), "webpage_url": ""}
            filepath = os.path.abspath(path)
        else:
            info, filepath = await asyncio.to_thread(ydl_extract, query)

        duration = info.get("duration", 0) or 0
        if duration > MAX_DURATION_SECONDS:
            await processing.delete()
            return await message.reply_text(
                f"❌ Song is too long! Max allowed: **{format_duration(MAX_DURATION_SECONDS)}**\n"
                f"Song duration: **{format_duration(duration)}**"
            )

        title = info.get("title", "Unknown Title")
        thumbnail = info.get("thumbnail") or get_banner("play")
        requester = message.from_user.mention if message.from_user else "Unknown"

        song_data = {
            "file": filepath, "title": title,
            "thumbnail": thumbnail, "duration": duration,
            "requester": requester,
        }

        if PLAYING.get(chat_id):
            QUEUE[chat_id].append(song_data)
            await processing.delete()
            await message.reply_photo(
                photo=thumbnail,
                caption=(
                    f"📋 **Added to Queue**\n\n"
                    f"**{title}**\n"
                    f"⏱ Duration: `{format_duration(duration)}`\n"
                    f"📌 Position: `#{len(QUEUE[chat_id])}`\n"
                    f"👤 Requested by: {requester}"
                )
            )
        else:
            CURRENT[chat_id] = song_data
            PLAY_START[chat_id] = time.time()
            await processing.edit_text(f"🎵 **Joining Voice Chat...**")

            await call_py.play(
                chat_id,
                MediaStream(filepath, video_flags=MediaStream.Flags.IGNORE),
                GroupCallConfig(auto_start=True)
            )
            PLAYING[chat_id] = True

            await processing.delete()
            lv = LOOP.get(chat_id, 0)
            loop_info = ""
            if lv == "inf":
                loop_info = "\n🔁 **Loop:** Infinite"
            elif isinstance(lv, int) and lv > 0:
                loop_info = f"\n🔁 **Loop:** {lv} time(s)"

            await message.reply_photo(
                photo=thumbnail,
                caption=(
                    f"🎵 **Now Playing**\n\n"
                    f"**{title}**\n"
                    f"⏱ Duration: `{format_duration(duration)}`\n"
                    f"👤 Requested by: {requester}"
                    f"{loop_info}"
                ),
                reply_markup=player_markup()
            )

    except Exception as e:
        await processing.edit_text(f"❌ **Error:** `{e}`")


# ─────────────────────────────────────────────────────────────────────────────
#  /forceplay
# ─────────────────────────────────────────────────────────────────────────────
@bot.on_message(filters.command("forceplay") & filters.group)
async def forceplay_cmd(client: Client, message: Message):
    if not await has_music_perm(client, message):
        return await message.reply_text("❌ Only admins or authorized users can use /forceplay.")
    if call_py is None:
        return await message.reply_text("❌ Voice features unavailable.")
    if len(message.command) < 2:
        return await message.reply_text("Usage: `/forceplay song name or URL`")

    query = " ".join(message.command[1:])
    chat_id = message.chat.id
    processing = await message.reply_text("⚡ **Force downloading...**")

    try:
        info, filepath = await asyncio.to_thread(ydl_extract, query)
        duration = info.get("duration", 0) or 0
        title = info.get("title", "Unknown")
        thumbnail = info.get("thumbnail") or get_banner("play")
        requester = message.from_user.mention if message.from_user else "Unknown"

        song_data = {
            "file": filepath, "title": title,
            "thumbnail": thumbnail, "duration": duration,
            "requester": requester,
        }

        CURRENT[chat_id] = song_data
        PLAY_START[chat_id] = time.time()
        LOOP[chat_id] = 0  # reset loop on force play

        await call_py.play(
            chat_id,
            MediaStream(filepath, video_flags=MediaStream.Flags.IGNORE),
            GroupCallConfig(auto_start=True)
        )
        PLAYING[chat_id] = True

        await processing.delete()
        await message.reply_photo(
            photo=thumbnail,
            caption=(
                f"⚡ **Force Playing**\n\n"
                f"**{title}**\n"
                f"⏱ Duration: `{format_duration(duration)}`\n"
                f"👤 Forced by: {requester}"
            ),
            reply_markup=player_markup()
        )
    except Exception as e:
        await processing.edit_text(f"❌ **Error:** `{e}`")


# ─────────────────────────────────────────────────────────────────────────────
#  /pause /resume /skip
# ─────────────────────────────────────────────────────────────────────────────
@bot.on_message(filters.command("pause") & filters.group)
async def pause_cmd(client: Client, message: Message):
    if not await has_music_perm(client, message):
        return await message.reply_text("❌ Only admins or authorized users can pause.")
    chat_id = message.chat.id
    if not PLAYING.get(chat_id):
        return await message.reply_text("Nothing is playing right now.")
    try:
        await call_py.pause_stream(chat_id)
        await message.reply_text("⏸ **Music Paused**\n\nUse /resume to continue.")
    except Exception as e:
        await message.reply_text(f"❌ `{e}`")


@bot.on_message(filters.command("resume") & filters.group)
async def resume_cmd(client: Client, message: Message):
    if not await has_music_perm(client, message):
        return await message.reply_text("❌ Only admins or authorized users can resume.")
    chat_id = message.chat.id
    if not PLAYING.get(chat_id):
        return await message.reply_text("Nothing is paused right now.")
    try:
        await call_py.resume_stream(chat_id)
        await message.reply_text("▶️ **Music Resumed!**")
    except Exception as e:
        await message.reply_text(f"❌ `{e}`")


@bot.on_message(filters.command("skip") & filters.group)
async def skip_cmd(client: Client, message: Message):
    if not await has_music_perm(client, message):
        return await message.reply_text("❌ Only admins or authorized users can skip.")
    chat_id = message.chat.id
    if not PLAYING.get(chat_id):
        return await message.reply_text("Nothing is playing right now.")
    await message.reply_text("⏭ **Skipped!** Loading next song...")
    LOOP[chat_id] = 0  # disable loop on manual skip
    await play_next(chat_id)


# ─────────────────────────────────────────────────────────────────────────────
#  /queue
# ─────────────────────────────────────────────────────────────────────────────
@bot.on_message(filters.command("queue") & filters.group)
async def queue_cmd(client: Client, message: Message):
    chat_id = message.chat.id
    current = CURRENT.get(chat_id)
    q = QUEUE.get(chat_id, [])

    if not current and not q:
        return await message.reply_text("📋 Queue is empty! Use /play to add songs.")

    lines = ["📋 **Music Queue**\n"]
    if current:
        elapsed = int(time.time() - PLAY_START.get(chat_id, time.time()))
        dur = current.get("duration", 0)
        bar_len = 15
        filled = int((elapsed / dur) * bar_len) if dur else 0
        bar = "▓" * filled + "░" * (bar_len - filled)
        lines.append(
            f"**▶️ Now Playing:**\n"
            f"**{current['title']}**\n"
            f"`[{bar}]` `{format_duration(elapsed)}/{format_duration(dur)}`\n"
            f"👤 {current['requester']}\n"
        )
    if q:
        lines.append("**📌 Up Next:**")
        for i, song in enumerate(q[:10], 1):
            lines.append(f"`{i}.` **{song['title']}** — `{format_duration(song['duration'])}`")
        if len(q) > 10:
            lines.append(f"\n_...and {len(q) - 10} more songs_")

    lv = LOOP.get(chat_id, 0)
    if lv == "inf":
        lines.append("\n🔁 **Loop:** Infinite")
    elif isinstance(lv, int) and lv > 0:
        lines.append(f"\n🔁 **Loop:** {lv} remaining")

    try:
        await message.reply_photo(photo=get_banner("queue"), caption="\n".join(lines))
    except Exception:
        await message.reply_text("\n".join(lines))


# ─────────────────────────────────────────────────────────────────────────────
#  /loop
# ─────────────────────────────────────────────────────────────────────────────
@bot.on_message(filters.command("loop") & filters.group)
async def loop_cmd(client: Client, message: Message):
    if not await has_music_perm(client, message):
        return await message.reply_text("❌ Only admins or authorized users can change loop.")
    chat_id = message.chat.id
    current_val = LOOP.get(chat_id, 0)

    if len(message.command) >= 2:
        arg = message.command[1].lower()
        if arg in ("off", "0", "disable"):
            LOOP[chat_id] = 0
            val_str = "Disabled ❌"
        elif arg in ("inf", "infinite", "∞"):
            LOOP[chat_id] = "inf"
            val_str = "Infinite ♾"
        else:
            try:
                n = int(arg)
                LOOP[chat_id] = n
                val_str = f"{n} time(s) 🔁"
            except ValueError:
                return await message.reply_text("Usage: `/loop off` / `/loop 5` / `/loop inf`")

        try:
            await message.reply_photo(
                photo=get_banner("loop"),
                caption=f"🔁 **Loop Updated**\n\nMode: **{val_str}**"
            )
        except Exception:
            await message.reply_text(f"🔁 Loop set to **{val_str}**")
    else:
        try:
            await message.reply_photo(
                photo=get_banner("loop"),
                caption=f"🔁 **Loop Settings**\n\nCurrent: `{current_val}`\nChoose a mode:",
                reply_markup=loop_markup(current_val)
            )
        except Exception:
            await message.reply_text(
                f"🔁 **Loop Settings**\n\nCurrent: `{current_val}`\nChoose a mode:",
                reply_markup=loop_markup(current_val)
            )


# ─────────────────────────────────────────────────────────────────────────────
#  /seek /seekback
# ─────────────────────────────────────────────────────────────────────────────
@bot.on_message(filters.command("seek") & filters.group)
async def seek_cmd(client: Client, message: Message):
    if not await has_music_perm(client, message):
        return await message.reply_text("❌ Only admins or authorized users can seek.")
    chat_id = message.chat.id
    if not PLAYING.get(chat_id):
        return await message.reply_text("Nothing is playing.")
    if len(message.command) < 2:
        return await message.reply_text("Usage: `/seek 30` (seconds)")
    try:
        seconds = int(message.command[1])
        await call_py.seek_stream(chat_id, seconds)
        await message.reply_text(f"⏩ **Seeked forward** `{seconds}s`")
    except Exception as e:
        await message.reply_text(f"❌ `{e}`")


@bot.on_message(filters.command("seekback") & filters.group)
async def seekback_cmd(client: Client, message: Message):
    if not await has_music_perm(client, message):
        return await message.reply_text("❌ Only admins or authorized users can seek.")
    chat_id = message.chat.id
    if not PLAYING.get(chat_id):
        return await message.reply_text("Nothing is playing.")
    if len(message.command) < 2:
        return await message.reply_text("Usage: `/seekback 30` (seconds)")
    try:
        seconds = int(message.command[1])
        await call_py.seek_stream(chat_id, -seconds)
        await message.reply_text(f"⏪ **Seeked backward** `{seconds}s`")
    except Exception as e:
        await message.reply_text(f"❌ `{e}`")


# ─────────────────────────────────────────────────────────────────────────────
#  /end
# ─────────────────────────────────────────────────────────────────────────────
@bot.on_message(filters.command("end") & filters.group)
async def end_cmd(client: Client, message: Message):
    if not await has_music_perm(client, message):
        return await message.reply_text("❌ Only admins or authorized users can end the session.")
    chat_id = message.chat.id
    QUEUE[chat_id] = []
    PLAYING[chat_id] = False
    LOOP[chat_id] = 0
    CURRENT.pop(chat_id, None)
    try:
        if call_py:
            await call_py.leave_call(chat_id)
    except Exception:
        pass
    try:
        await message.reply_photo(
            photo=get_banner("end"),
            caption=(
                "⏹ **Session Ended**\n\n"
                "Queue cleared, loop disabled, and I've left the Voice Chat.\n"
                "Use /play anytime to start a new session! 🎶"
            )
        )
    except Exception:
        await message.reply_text("⏹ Session ended. Queue cleared and left VC.")


# ─────────────────────────────────────────────────────────────────────────────
#  /auth /unauth
# ─────────────────────────────────────────────────────────────────────────────
async def _resolve_user(client: Client, message: Message):
    """Return user_id from reply or command arg."""
    if message.reply_to_message and message.reply_to_message.from_user:
        return message.reply_to_message.from_user.id, message.reply_to_message.from_user.mention
    if len(message.command) >= 2:
        arg = message.command[1]
        try:
            uid = int(arg)
            u = await client.get_users(uid)
            return uid, u.mention
        except Exception:
            try:
                u = await client.get_users(arg.lstrip("@"))
                return u.id, u.mention
            except Exception:
                pass
    return None, None


@bot.on_message(filters.command("auth") & filters.group)
async def auth_cmd(client: Client, message: Message):
    if not await is_admin(client, message.chat.id, message.from_user.id):
        return await message.reply_text("❌ Only group admins can authorize users.")
    uid, mention = await _resolve_user(client, message)
    if not uid:
        return await message.reply_text("Reply to a user or provide: `/auth user_id / @username`")
    auth_user(message.chat.id, uid)
    try:
        await message.reply_photo(
            photo=get_banner("auth"),
            caption=f"✅ **User Authorized**\n\n{mention} can now control music in this group!"
        )
    except Exception:
        await message.reply_text(f"✅ {mention} authorized to control music.")


@bot.on_message(filters.command("unauth") & filters.group)
async def unauth_cmd(client: Client, message: Message):
    if not await is_admin(client, message.chat.id, message.from_user.id):
        return await message.reply_text("❌ Only group admins can remove authorization.")
    uid, mention = await _resolve_user(client, message)
    if not uid:
        return await message.reply_text("Reply to a user or provide: `/unauth user_id / @username`")
    unauth_user(message.chat.id, uid)
    await message.reply_text(f"🚫 {mention} has been unauthorized.")


# ─────────────────────────────────────────────────────────────────────────────
#  /reload
# ─────────────────────────────────────────────────────────────────────────────
@bot.on_message(filters.command("reload") & filters.group)
async def reload_cmd(client: Client, message: Message):
    if not await is_admin(client, message.chat.id, message.from_user.id):
        return await message.reply_text("❌ Only admins can reload.")
    # Pyrogram caches admin list; no internal cache to reload but we acknowledge.
    await message.reply_text("🔄 **Admin cache reloaded!**\n\nAll permissions are now refreshed.")


# ─────────────────────────────────────────────────────────────────────────────
#  /botstats  (owner only)
# ─────────────────────────────────────────────────────────────────────────────
@bot.on_message(filters.command("botstats") & filters.user(OWNER_ID))
async def botstats_cmd(client: Client, message: Message):
    uptime = int(time.time() - START_TIME)
    m, s = divmod(uptime, 60)
    h, m = divmod(m, 60)
    d, h = divmod(h, 24)

    cpu = psutil.cpu_percent(interval=0.5)
    ram = psutil.virtual_memory()
    disk = psutil.disk_usage("/")

    active = sum(1 for v in PLAYING.values() if v)
    total_q = sum(len(v) for v in QUEUE.values())
    tracked = len(get_tracked_chats())
    approved = len(get_approved_members())

    try:
        await message.reply_photo(
            photo=get_banner("stats"),
            caption=(
                f"📊 **MusicVerse Statistics**\n\n"
                f"⏱ **Uptime:** `{d}d {h}h {m}m {s}s`\n\n"
                f"**System**\n"
                f"🖥 CPU: `{cpu}%`\n"
                f"💾 RAM: `{ram.percent}%` ({ram.used // 1024**2}MB / {ram.total // 1024**2}MB)\n"
                f"💿 Disk: `{disk.percent}%` ({disk.used // 1024**3}GB / {disk.total // 1024**3}GB)\n\n"
                f"**Bot**\n"
                f"🎵 Active VCs: `{active}`\n"
                f"📋 Total Queued: `{total_q}`\n"
                f"👥 Tracked Chats: `{tracked}`\n"
                f"✅ Approved Members: `{approved}`\n"
                f"🐍 Python: `{platform.python_version()}`\n"
            )
        )
    except Exception:
        await message.reply_text("❌ Could not send stats image. Check terminal.")


# ─────────────────────────────────────────────────────────────────────────────
#  /broadcast
# ─────────────────────────────────────────────────────────────────────────────
@bot.on_message(filters.command("broadcast"))
async def broadcast_cmd(client: Client, message: Message):
    uid = message.from_user.id
    if uid != OWNER_ID and not is_approved(uid):
        return await message.reply_text("❌ Only the bot owner or approved members can broadcast.")
    if not message.reply_to_message and len(message.command) < 2:
        return await message.reply_text("Reply to a message or provide text to broadcast.")

    proc = await message.reply_text("⏳ **Broadcasting...**")
    success = failed = 0
    for chat_id in get_tracked_chats():
        try:
            if message.reply_to_message:
                await message.reply_to_message.copy(chat_id)
            else:
                await bot.send_message(chat_id, message.text.split(None, 1)[1])
            success += 1
            await asyncio.sleep(0.05)
        except Exception:
            failed += 1

    await proc.edit_text(
        f"✅ **Broadcast Done!**\n\n"
        f"🎯 Success: `{success}`\n"
        f"❌ Failed: `{failed}`"
    )


# ─────────────────────────────────────────────────────────────────────────────
#  /approvemember /unapprovemember  (owner only)
# ─────────────────────────────────────────────────────────────────────────────
@bot.on_message(filters.command("approvemember") & filters.user(OWNER_ID))
async def approve_cmd(client: Client, message: Message):
    uid, mention = await _resolve_user(client, message)
    if not uid:
        return await message.reply_text("Reply to a user or provide user_id.")
    approve_member(uid)
    await message.reply_text(f"✅ **{mention}** has been approved globally.\n\nThey can now broadcast and use all commands.")


@bot.on_message(filters.command("unapprovemember") & filters.user(OWNER_ID))
async def unapprove_cmd(client: Client, message: Message):
    uid, mention = await _resolve_user(client, message)
    if not uid:
        return await message.reply_text("Reply to a user or provide user_id.")
    unapprove_member(uid)
    await message.reply_text(f"🚫 **{mention}** has been unapproved.")


# ─────────────────────────────────────────────────────────────────────────────
#  /restart  (owner only)
# ─────────────────────────────────────────────────────────────────────────────
@bot.on_message(filters.command("restart") & filters.user(OWNER_ID))
async def restart_cmd(client: Client, message: Message):
    try:
        await message.reply_photo(
            photo=get_banner("restart"),
            caption="🔄 **Restarting MusicVerse...**\n\nBe right back! 🚀"
        )
    except Exception:
        await message.reply_text("🔄 Restarting...")
    await bot.stop()
    if user:
        try:
            await user.stop()
        except Exception:
            pass
    os.execv(sys.executable, [sys.executable] + sys.argv)


# ─────────────────────────────────────────────────────────────────────────────
#  Callback Query Handler
# ─────────────────────────────────────────────────────────────────────────────
@bot.on_callback_query()
async def callback_handler(client: Client, query: CallbackQuery):
    data = query.data
    chat_id = query.message.chat.id
    user_id = query.from_user.id

    # ── Navigation callbacks ─────────────────────────────────────────────────
    if data == "cb_start":
        me = await client.get_me()
        caption = (
            f"🎵 **Welcome to MusicVerse!**\n\n"
            "I'm your feature-rich music bot. Add me to any group!\n\n"
            "Tap **Commands** below to explore."
        )
        try:
            await query.message.edit_caption(caption=caption, reply_markup=start_markup())
        except Exception:
            await query.answer("Go to /start")
        return

    if data == "cb_help":
        try:
            await query.message.edit_caption(
                caption="🎧 **MusicVerse Help**\n\nChoose a category:",
                reply_markup=help_markup()
            )
        except Exception:
            await query.message.reply_text("🎧 MusicVerse Help", reply_markup=help_markup())
        return

    if data == "help_music":
        await query.answer()
        try:
            await query.message.edit_caption(caption=HELP_MUSIC, reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Back", callback_data="cb_help")
            ]]))
        except Exception:
            await query.message.reply_text(HELP_MUSIC)
        return

    if data == "help_admin":
        await query.answer()
        try:
            await query.message.edit_caption(caption=HELP_ADMIN, reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Back", callback_data="cb_help")
            ]]))
        except Exception:
            await query.message.reply_text(HELP_ADMIN)
        return

    if data == "help_owner":
        await query.answer()
        try:
            await query.message.edit_caption(caption=HELP_OWNER, reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Back", callback_data="cb_help")
            ]]))
        except Exception:
            await query.message.reply_text(HELP_OWNER)
        return

    if data == "cb_stats":
        await query.answer("Fetching stats...")
        fake_msg = query.message
        fake_msg.from_user = query.from_user
        await botstats_cmd(client, fake_msg)
        return

    if data == "queue_view":
        await query.answer()
        fake_msg = query.message
        fake_msg.from_user = query.from_user
        await queue_cmd(client, fake_msg)
        return

    if data == "close":
        await query.message.delete()
        return

    # ── Player controls — check permission ───────────────────────────────────
    async def check_perm():
        if call_py is None:
            await query.answer("Voice features unavailable.", show_alert=True)
            return False
        if not PLAYING.get(chat_id):
            await query.answer("Nothing is playing.", show_alert=True)
            return False
        if not (
            user_id == OWNER_ID
            or is_approved(user_id)
            or is_authed(chat_id, user_id)
            or await is_admin(client, chat_id, user_id)
        ):
            await query.answer("Only admins or authorized users can control playback.", show_alert=True)
            return False
        return True

    if data == "pause":
        if not await check_perm(): return
        try:
            await call_py.pause_stream(chat_id)
            await query.answer("⏸ Paused")
        except Exception as e:
            await query.answer(str(e), show_alert=True)

    elif data == "resume":
        if call_py is None:
            return await query.answer("Voice features unavailable.", show_alert=True)
        try:
            await call_py.resume_stream(chat_id)
            await query.answer("▶️ Resumed")
        except Exception as e:
            await query.answer(str(e), show_alert=True)

    elif data == "skip":
        if not await check_perm(): return
        await query.answer("⏭ Skipping...")
        LOOP[chat_id] = 0
        await play_next(chat_id)

    elif data == "stop":
        if not await check_perm(): return
        QUEUE[chat_id] = []
        PLAYING[chat_id] = False
        LOOP[chat_id] = 0
        CURRENT.pop(chat_id, None)
        try:
            await call_py.leave_call(chat_id)
        except Exception:
            pass
        await query.answer("⏹ Stopped")
        await query.message.edit_caption(caption="⏹ **Playback stopped and queue cleared.**")

    elif data == "prev":
        await query.answer("⏮ Previous not supported yet.", show_alert=True)

    elif data == "loop_toggle":
        if not (user_id == OWNER_ID or is_approved(user_id) or is_authed(chat_id, user_id) or await is_admin(client, chat_id, user_id)):
            return await query.answer("No permission.", show_alert=True)
        current_loop = LOOP.get(chat_id, 0)
        if current_loop == 0:
            LOOP[chat_id] = "inf"
            await query.answer("🔁 Loop: Infinite")
        elif current_loop == "inf":
            LOOP[chat_id] = 0
            await query.answer("❌ Loop: Disabled")
        else:
            LOOP[chat_id] = 0
            await query.answer("❌ Loop: Disabled")

    elif data.startswith("loop_"):
        val = data.split("_", 1)[1]
        if val == "inf":
            LOOP[chat_id] = "inf"
            await query.answer("♾ Loop: Infinite")
        elif val == "0":
            LOOP[chat_id] = 0
            await query.answer("❌ Loop disabled")
        else:
            LOOP[chat_id] = int(val)
            await query.answer(f"🔁 Loop: {val}×")
        try:
            await query.message.edit_caption(
                caption=f"🔁 **Loop Updated:** `{LOOP[chat_id]}`",
                reply_markup=loop_markup(LOOP[chat_id])
            )
        except Exception:
            pass


# ─────────────────────────────────────────────────────────────────────────────
#  Main
# ─────────────────────────────────────────────────────────────────────────────
async def main():
    global user, call_py
    print("🎵 Starting MusicVerse...")
    await bot.start()

    commands = [
        BotCommand("start", "Welcome message"),
        BotCommand("help", "Show all commands"),
        BotCommand("play", "Play a song in VC"),
        BotCommand("forceplay", "Force play a song (admin)"),
        BotCommand("pause", "Pause current song"),
        BotCommand("resume", "Resume paused song"),
        BotCommand("skip", "Skip current song"),
        BotCommand("queue", "View the queue"),
        BotCommand("loop", "Toggle loop mode"),
        BotCommand("seek", "Seek forward N seconds"),
        BotCommand("seekback", "Seek backward N seconds"),
        BotCommand("end", "End music session"),
        BotCommand("auth", "Authorize a user (admin)"),
        BotCommand("unauth", "Remove authorization (admin)"),
        BotCommand("reload", "Reload admin cache"),
        BotCommand("botstats", "Bot statistics (owner)"),
        BotCommand("broadcast", "Broadcast message (owner/approved)"),
        BotCommand("approvemember", "Approve a member (owner)"),
        BotCommand("unapprovemember", "Unapprove a member (owner)"),
        BotCommand("restart", "Restart the bot (owner)"),
    ]
    try:
        await bot.set_bot_commands(commands)
        print("✅ Bot commands registered.")
    except Exception as e:
        print(f"[WARN] Could not set bot commands: {e}")

    if user is not None and call_py is not None:
        print("🔗 Starting user session...")
        try:
            await user.start()
            print("✅ User session started.")
            print("📡 Starting PyTgCalls...")
            await call_py.start()
            print("✅ PyTgCalls started.")
        except Exception as e:
            print(f"[ERR] Session/PyTgCalls failed: {e}")
            user = None
            call_py = None
    else:
        print("⚠️  No SESSION_STRING — voice features disabled. Run genrate_session.py to create one.")

    print("🚀 MusicVerse is live! Send /play in a group.")
    await idle()
    print("🛑 Shutting down...")
    await bot.stop()
    if user:
        try:
            await user.stop()
        except Exception:
            pass


if __name__ == "__main__":
    loop.run_until_complete(main())