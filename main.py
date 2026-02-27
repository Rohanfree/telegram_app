"""
Main Application - FastAPI Server with WebSocket support
"""
import os
import asyncio
import logging
import secrets
from pathlib import Path
from datetime import datetime
from contextlib import asynccontextmanager
from typing import Dict, Optional
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Request, Form
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, RedirectResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from dotenv import load_dotenv

from websocket_manager import ws_manager
from telegram_bot import TelegramBot
from pyrogram_handler import create_pyrogram_handler

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Always resolve paths relative to this file's location, not the CWD at launch.
# This ensures static/ and downloads/ are found when VS Code runs from a parent dir.
_HERE = Path(__file__).parent
os.chdir(_HERE)

# Load environment variables from the project's .env
load_dotenv(_HERE / ".env")

# Get configuration
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ALLOWED_CHAT_IDS = os.getenv("ALLOWED_CHAT_IDS", "")
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8000"))

# Downloads directory (configurable)
DOWNLOADS_DIR = Path(os.getenv("DOWNLOADS_DIR", "downloads"))
DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)
logger.info(f"Downloads directory: {DOWNLOADS_DIR.resolve()}")

# Dashboard auth credentials
DASHBOARD_USERNAME = os.getenv("DASHBOARD_USERNAME", "admin")
DASHBOARD_PASSWORD = os.getenv("DASHBOARD_PASSWORD", "changeme")

# Simple in-memory session store: token → username
_sessions: Dict[str, str] = {}

# Parse allowed chat IDs
allowed_chat_ids = None
if ALLOWED_CHAT_IDS:
    try:
        allowed_chat_ids = [int(chat_id.strip()) for chat_id in ALLOWED_CHAT_IDS.split(",")]
        logger.info(f"Allowed chat IDs: {allowed_chat_ids}")
    except ValueError:
        logger.warning("Invalid ALLOWED_CHAT_IDS format. Allowing all users.")

# Initialize handlers
telegram_bot = None
pyrogram_handler = None


# ─── Auth helpers ────────────────────────────────────────────────────────────

def _get_session_user(request: Request) -> Optional[str]:
    """Return the logged-in username from cookie, or None."""
    token = request.cookies.get("session_token")
    return _sessions.get(token) if token else None


# ─── Auth middleware ──────────────────────────────────────────────────────────

class AuthMiddleware(BaseHTTPMiddleware):
    """Redirect unauthenticated requests to /login."""

    PUBLIC_PATHS = {"/login", "/logout", "/static", "/health", "/favicon.ico"}

    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # Allow public paths and anything under /static
        if path in self.PUBLIC_PATHS or path.startswith("/static"):
            return await call_next(request)

        # WebSocket — return 403 if not authenticated
        if path == "/ws":
            token = request.cookies.get("session_token")
            if not token or token not in _sessions:
                return HTMLResponse("Unauthorized", status_code=403)
            return await call_next(request)

        # All other routes require login
        token = request.cookies.get("session_token")
        if not token or token not in _sessions:
            return RedirectResponse(url="/login", status_code=302)

        return await call_next(request)


# ─── Lifespan ────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifecycle"""
    global telegram_bot, pyrogram_handler
    
    # Startup
    logger.info("Starting application...")

    # Start Pyrogram client (if credentials are configured)
    pyrogram_handler = create_pyrogram_handler(TELEGRAM_BOT_TOKEN, DOWNLOADS_DIR)
    if pyrogram_handler:
        try:
            await pyrogram_handler.start(
                broadcast_progress=ws_manager.broadcast_download_progress,
                broadcast_file_received=ws_manager.broadcast_file_received,
            )
            logger.info("Pyrogram client started — large file downloads enabled (up to 4 GB)")
        except Exception as e:
            logger.error(f"Failed to start Pyrogram client: {e}")
            pyrogram_handler = None

    
    # Validate configuration
    if not TELEGRAM_BOT_TOKEN or TELEGRAM_BOT_TOKEN == "your_bot_token_here":
        logger.error("TELEGRAM_BOT_TOKEN not set! Please configure .env file.")
    else:
        telegram_bot = TelegramBot(
            TELEGRAM_BOT_TOKEN,
            allowed_chat_ids,
            pyrogram_handler,
            downloads_dir=DOWNLOADS_DIR,
        )
        asyncio.create_task(telegram_bot.start_polling())
    
    logger.info(f"Dashboard available at http://{HOST}:{PORT}")
    
    yield
    
    # Shutdown
    logger.info("Shutting down application...")
    if telegram_bot:
        await telegram_bot.stop_polling()
    if pyrogram_handler:
        await pyrogram_handler.stop()


# ─── App setup ───────────────────────────────────────────────────────────────

app = FastAPI(
    title="Telegram Dashboard",
    description="Real-time dashboard for Telegram bot",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(AuthMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── Auth routes ─────────────────────────────────────────────────────────────

@app.get("/login")
async def login_page():
    """Serve the login page"""
    return FileResponse("static/login.html")


@app.post("/login")
async def login(
    username: str = Form(...),
    password: str = Form(...),
):
    """Validate credentials and set session cookie"""
    if username == DASHBOARD_USERNAME and password == DASHBOARD_PASSWORD:
        token = secrets.token_urlsafe(32)
        _sessions[token] = username
        response = RedirectResponse(url="/", status_code=302)
        response.set_cookie(
            key="session_token",
            value=token,
            httponly=True,
            samesite="lax",
            max_age=60 * 60 * 24 * 7,  # 7 days
        )
        return response
    return RedirectResponse(url="/login?error=1", status_code=302)


@app.get("/logout")
async def logout(request: Request):
    """Clear session and redirect to login"""
    token = request.cookies.get("session_token")
    if token:
        _sessions.pop(token, None)
    response = RedirectResponse(url="/login", status_code=302)
    response.delete_cookie("session_token")
    return response


# ─── Dashboard routes ─────────────────────────────────────────────────────────

@app.get("/")
async def read_root():
    """Serve the dashboard HTML"""
    return FileResponse("static/index.html")


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "telegram_bot": telegram_bot is not None,
        "websocket_connections": len(ws_manager.active_connections)
    }


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time updates"""
    await ws_manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            logger.info(f"Received from client: {data}")
            await ws_manager.send_to_client(websocket, {
                "type": "pong",
                "message": "Server received your message"
            })
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
        logger.info("Client disconnected")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        ws_manager.disconnect(websocket)


@app.get("/downloads")
async def list_downloads():
    """List all downloaded files"""
    files = []
    if DOWNLOADS_DIR.exists():
        for f in sorted(DOWNLOADS_DIR.iterdir()):
            if f.is_file():
                stat = f.stat()
                files.append({
                    "name": f.name,
                    "size": stat.st_size,
                    "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                })
    return files


@app.get("/downloads/{filename}")
async def download_file(filename: str):
    """Download a specific file"""
    file_path = DOWNLOADS_DIR / filename
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    if not file_path.resolve().is_relative_to(DOWNLOADS_DIR.resolve()):
        raise HTTPException(status_code=400, detail="Invalid filename")
    return FileResponse(path=str(file_path), filename=filename)


@app.delete("/downloads/{filename}")
async def delete_file(filename: str):
    """Delete a specific downloaded file"""
    file_path = DOWNLOADS_DIR / filename
    if not file_path.resolve().is_relative_to(DOWNLOADS_DIR.resolve()):
        raise HTTPException(status_code=400, detail="Invalid filename")
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    file_path.unlink()
    logger.info(f"Deleted file: {filename}")
    return {"deleted": filename}


@app.get("/stream/{filename}")
async def stream_file(filename: str, request: Request):
    """Stream / preview a file inline in the browser with range-request support."""
    import mimetypes
    from fastapi.responses import StreamingResponse, Response

    file_path = DOWNLOADS_DIR / filename
    if not file_path.resolve().is_relative_to(DOWNLOADS_DIR.resolve()):
        raise HTTPException(status_code=400, detail="Invalid filename")
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")

    mime, _ = mimetypes.guess_type(str(file_path))
    if not mime:
        mime = "application/octet-stream"

    file_size = file_path.stat().st_size
    range_header = request.headers.get("range")

    if range_header:
        # Parse "bytes=start-end"
        try:
            byte_range = range_header.replace("bytes=", "").split("-")
            start = int(byte_range[0])
            end = int(byte_range[1]) if byte_range[1] else file_size - 1
        except (ValueError, IndexError):
            raise HTTPException(status_code=416, detail="Invalid range")

        if start >= file_size:
            raise HTTPException(status_code=416, detail="Range not satisfiable")

        # Clamp end to file_size-1 per RFC 7233 (browsers often send end > file_size)
        end = min(end, file_size - 1)

        chunk_size = end - start + 1

        def iter_file():
            with open(file_path, "rb") as f:
                f.seek(start)
                remaining = chunk_size
                while remaining > 0:
                    data = f.read(min(65536, remaining))
                    if not data:
                        break
                    remaining -= len(data)
                    yield data

        headers = {
            "Content-Range": f"bytes {start}-{end}/{file_size}",
            "Accept-Ranges": "bytes",
            "Content-Length": str(chunk_size),
            "Content-Disposition": f'inline; filename="{filename}"',
        }
        return StreamingResponse(iter_file(), status_code=206, headers=headers, media_type=mime)

    # Full file response
    def iter_full():
        with open(file_path, "rb") as f:
            while chunk := f.read(65536):
                yield chunk

    headers = {
        "Accept-Ranges": "bytes",
        "Content-Length": str(file_size),
        "Content-Disposition": f'inline; filename="{filename}"',
    }
    return StreamingResponse(iter_full(), headers=headers, media_type=mime)


# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")


if __name__ == "__main__":
    import uvicorn
    
    if not TELEGRAM_BOT_TOKEN or TELEGRAM_BOT_TOKEN == "your_bot_token_here":
        print("\n" + "="*60)
        print("⚠️  CONFIGURATION REQUIRED")
        print("="*60)
        print("Please configure your .env file before running.")
        print("="*60 + "\n")
    
    uvicorn.run(
        "main:app",
        host=HOST,
        port=PORT,
        reload=os.getenv("RELOAD", "false").lower() == "true",
        log_level="info"
    )

