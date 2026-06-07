"""
database.py — lightweight JSON-based persistence for MusicVerse
Stores: auth_users, approved_members, loop state, tracked chats
"""
import json, os

DB_PATH = "musicverse_db.json"

_DEFAULT = {
    "auth_users": {},       # { "chat_id": [user_id, ...] }
    "approved_members": [], # [user_id, ...]  — can broadcast + use all cmds
    "tracked_chats": [],    # [chat_id, ...]
}

def _load() -> dict:
    if os.path.exists(DB_PATH):
        try:
            with open(DB_PATH) as f:
                data = json.load(f)
                # back-fill missing keys
                for k, v in _DEFAULT.items():
                    if k not in data:
                        data[k] = v
                return data
        except Exception:
            pass
    return dict(_DEFAULT)

def _save(data: dict):
    with open(DB_PATH, "w") as f:
        json.dump(data, f, indent=2)

# ── Tracked Chats ─────────────────────────────────────────────────────────────
def add_tracked_chat(chat_id: int):
    db = _load()
    if chat_id not in db["tracked_chats"]:
        db["tracked_chats"].append(chat_id)
        _save(db)

def get_tracked_chats() -> list:
    return _load()["tracked_chats"]

# ── Auth Users (per-group) ────────────────────────────────────────────────────
def auth_user(chat_id: int, user_id: int):
    db = _load()
    key = str(chat_id)
    db["auth_users"].setdefault(key, [])
    if user_id not in db["auth_users"][key]:
        db["auth_users"][key].append(user_id)
    _save(db)

def unauth_user(chat_id: int, user_id: int):
    db = _load()
    key = str(chat_id)
    if key in db["auth_users"] and user_id in db["auth_users"][key]:
        db["auth_users"][key].remove(user_id)
        _save(db)

def is_authed(chat_id: int, user_id: int) -> bool:
    db = _load()
    return user_id in db["auth_users"].get(str(chat_id), [])

# ── Approved Members (global, by owner) ───────────────────────────────────────
def approve_member(user_id: int):
    db = _load()
    if user_id not in db["approved_members"]:
        db["approved_members"].append(user_id)
        _save(db)

def unapprove_member(user_id: int):
    db = _load()
    if user_id in db["approved_members"]:
        db["approved_members"].remove(user_id)
        _save(db)

def is_approved(user_id: int) -> bool:
    return user_id in _load()["approved_members"]

def get_approved_members() -> list:
    return _load()["approved_members"]
