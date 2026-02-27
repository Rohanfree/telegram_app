# Telegram Dashboard

A real-time web dashboard for your Telegram bot — receive files, monitor activity, and manage downloads through a live WebSocket-powered UI.

![Python](https://img.shields.io/badge/Python-3.8+-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-0.109-green)

## Features

🤖 **Telegram Bot**
- Continuous polling for messages
- Receive and save files (documents, photos, videos, audio, voice)
- Large file support up to 4 GB via Pyrogram
- Optional user authorization by chat ID

📊 **Live Dashboard**
- Modern dark-themed UI with WebSocket live updates
- 💬 Conversation history
- 📊 Status monitoring
- 📝 Recent commands
- 📥 Downloads panel with file browser
- Auto-reconnection on connection loss

🔐 **Auth**
- Username/password login with session cookies

## Prerequisites

- Python 3.8+
- A Telegram Bot Token — get one from [@BotFather](https://t.me/botfather)

## Installation

```bash
# 1. Navigate to project directory
cd /Users/admin/Rohan/Python/telegram-gemini-dashboard

# 2. Create & activate virtual environment
python3 -m venv venv
source venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt
```

## Configuration

Edit `.env` with your settings:

```env
# Required
TELEGRAM_BOT_TOKEN=your_bot_token_here

# Optional: restrict to specific Telegram chat IDs (comma-separated)
ALLOWED_CHAT_IDS=

# Server
HOST=0.0.0.0
PORT=8000

# Dashboard login
DASHBOARD_USERNAME=admin
DASHBOARD_PASSWORD=changeme

# Downloads directory
DOWNLOADS_DIR=downloads

# Pyrogram (for large file downloads >20 MB, up to 4 GB)
# Get api_id & api_hash from https://my.telegram.org
PYROGRAM_API_ID=
PYROGRAM_API_HASH=
PYROGRAM_PHONE=
```

## Running the App

### Option 1 — Python (venv)

```bash
source venv/bin/activate
python main.py
```

Or with auto-reload for development:

```bash
source venv/bin/activate
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### Option 2 — Docker

```bash
docker-compose up --build
```

Open **http://localhost:8000** in your browser and log in with your dashboard credentials.

## Telegram Bot Commands

| Command | Description |
|---------|-------------|
| `/start` | Welcome message |
| `/help`  | Help information |

Send any **file** (document, photo, video, audio, voice) to the bot and it will be saved to the server and appear in the dashboard's Downloads panel.

## Project Structure

```
telegram-dashboard/
├── main.py               # FastAPI app & routes
├── telegram_bot.py       # Telegram bot polling & file handling
├── pyrogram_handler.py   # Large file downloader (MTProto)
├── websocket_manager.py  # WebSocket broadcast manager
├── requirements.txt      # Dependencies
├── .env                  # Your configuration
├── static/
│   ├── index.html        # Dashboard
│   ├── login.html        # Login page
│   ├── style.css         # Styles
│   └── app.js            # WebSocket client
└── downloads/            # Saved files
```

## Troubleshooting

**`uvicorn: command not found`** — activate the venv first: `source venv/bin/activate`

**Bot not responding** — check `TELEGRAM_BOT_TOKEN` in `.env` and verify it with @BotFather.

**Dashboard not connecting** — ensure the server is running and check the browser console for WebSocket errors.

## Security Notes

- Never commit your `.env` file — it contains your bot token
- Use `ALLOWED_CHAT_IDS` to restrict bot access
- Change the default `DASHBOARD_USERNAME` / `DASHBOARD_PASSWORD`
- Run behind a reverse proxy (nginx) with HTTPS for production

## Built With

- [FastAPI](https://fastapi.tiangolo.com/) — web framework
- [python-telegram-bot](https://python-telegram-bot.org/) — Telegram Bot API
- [Pyrogram](https://pyrogram.org/) — MTProto client for large files
- [WebSockets](https://websockets.readthedocs.io/) — real-time updates
