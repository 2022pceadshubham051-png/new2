# 🎵 MusicVerse — Full-Featured Telegram Music Bot

A powerful, feature-rich Telegram music bot that streams audio into Group Voice Chats.

---

## ✨ Features

| Category | Features |
|---|---|
| 🎵 **Playback** | Play by song name, YouTube URL, or reply to audio |
| 📋 **Queue** | Smart queue, auto-advances, max 50 songs |
| 🔁 **Loop** | Off / 1× / N× / Infinite |
| ⏩ **Seek** | Seek forward & backward by seconds |
| ⚡ **Force Play** | Admins can interrupt the queue |
| 👮 **Auth System** | Per-group authorized users |
| 👑 **Owner System** | Approved global members |
| 📡 **Auto-Leave** | Leaves VC if idle for 5 min |
| ⏱ **Duration Limit** | Max 1 hour per song |
| 📢 **Broadcast** | Owner/approved can message all chats |
| 📊 **Stats** | CPU, RAM, disk, active VCs |
| 🔔 **Support Logs** | Notifies a support group on new adds/users |

---

## 📁 File Structure

```
musicverse/
├── main.py            ← Main bot (all commands)
├── config.py          ← Credentials & settings
├── database.py        ← JSON-based persistence
├── helpers.py         ← Permission utilities
├── keyboards.py       ← All inline keyboards & banners
├── genrate_session.py ← Helper to generate SESSION_STRING
└── requirements.txt
```

---

## ⚙️ Setup

### 1. Install dependencies
```bash
pip install -r requirements.txt
```

### 2. Get credentials
- `API_ID` / `API_HASH` → https://my.telegram.org/apps
- `BOT_TOKEN` → @BotFather on Telegram
- `SESSION_STRING` → Run `python genrate_session.py` (uses a USER account to join VCs)

### 3. Fill in config.py
```python
API_ID      = "your_api_id"
API_HASH    = "your_api_hash"
BOT_TOKEN   = "your_bot_token"
SESSION_STRING = "your_session_string"
OWNER_ID    = 123456789           # Your Telegram user ID
SUPPORT_GROUP_ID = -100123456789  # Your support/log group (negative ID)
```

### 4. Add bot banners (optional)
Upload images to https://telegra.ph and update the `BANNERS` dict in `keyboards.py`.

### 5. Run
```bash
python main.py
```

---

## 🤖 Commands

### 🎵 Music
| Command | Description |
|---|---|
| `/play [name/url/reply]` | Play in VC |
| `/forceplay [song]` | Force play (admin/auth) |
| `/pause` | Pause current song |
| `/resume` | Resume playback |
| `/skip` | Skip to next song |
| `/queue` | View current queue |
| `/loop [off/1/5/10/inf]` | Set loop mode |
| `/seek [seconds]` | Seek forward |
| `/seekback [seconds]` | Seek backward |
| `/end` | End session & clear queue |

### 👮 Admin (Group Admins)
| Command | Description |
|---|---|
| `/auth [reply/@user/id]` | Authorize a non-admin for music control |
| `/unauth [reply/@user/id]` | Remove authorization |
| `/reload` | Refresh admin cache |

### 👑 Owner Only
| Command | Description |
|---|---|
| `/botstats` | Full system & bot stats |
| `/broadcast [text/reply]` | Broadcast to all tracked chats |
| `/approvemember [reply/id]` | Give global permissions |
| `/unapprovemember [reply/id]` | Remove global permissions |
| `/restart` | Restart the bot |

---

## 🔒 Permission Hierarchy

```
Bot Owner  >  Approved Members  >  Group Admins  >  Auth Users  >  Regular Users
```

- **Music control** (pause/resume/skip/seek/loop/end/forceplay): Admin, Auth, Approved, Owner
- **Auth management**: Group Admin+
- **Broadcast / Approve**: Approved Member or Owner
- **Owner commands**: Owner only

---

## 📝 Notes

- The bot uses a **Pyrogram User session** (`SESSION_STRING`) to join Voice Chats. This is required by Telegram — bots cannot join VCs directly.
- Songs are downloaded to the `downloads/` folder. You may want to set up a cron to clean old files.
- `musicverse_db.json` stores all persistent data (auth users, approved members, tracked chats).
