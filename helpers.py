"""
helpers.py — permission utils for MusicVerse
"""
from pyrogram import Client
from pyrogram.types import Message, ChatMember
from pyrogram.enums import ChatMemberStatus
from config import OWNER_ID
from database import is_authed, is_approved


async def is_admin(client: Client, chat_id: int, user_id: int) -> bool:
    """True if user is admin/owner in the group."""
    try:
        member: ChatMember = await client.get_chat_member(chat_id, user_id)
        return member.status in (
            ChatMemberStatus.ADMINISTRATOR,
            ChatMemberStatus.OWNER,
        )
    except Exception:
        return False


async def has_music_perm(client: Client, message: Message) -> bool:
    """True if the sender can control music (owner / admin / auth / approved)."""
    user_id = message.from_user.id
    chat_id = message.chat.id
    if user_id == OWNER_ID:
        return True
    if is_approved(user_id):
        return True
    if is_authed(chat_id, user_id):
        return True
    if await is_admin(client, chat_id, user_id):
        return True
    return False


def format_duration(seconds: int) -> str:
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"
