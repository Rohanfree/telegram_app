"""
Pyrogram Handler - Large file downloader using MTProto (no 20 MB limit).

Architecture:
  Pyrogram registers an outgoing-message handler on the user client.  When the
  user sends a large file to the bot, Pyrogram sees the *outgoing* message and
  downloads it directly via MTProto — bypassing the 20 MB Bot API limit.

  The Bot API handler (telegram_bot.py) calls `register_context()` with the
  `file_unique_id` (identical on both APIs) so Pyrogram can edit the Telegram
  status message and supply the correct filename / username.  Even if Pyrogram
  fires before the context is registered (race condition), it still downloads
  using sane defaults.
"""
import os
import asyncio
import logging
from pathlib import Path
from typing import Optional, Callable, Dict, Any

logger = logging.getLogger(__name__)

_pyrogram_available = False
try:
    from pyrogram import Client, filters
    from pyrogram.errors import FloodWait
    _pyrogram_available = True
except ImportError:
    logger.warning("pyrogram not installed — large file download unavailable")

# Bot API hard limit — files below this are handled by python-telegram-bot
MAX_BOT_FILE_SIZE = 20 * 1024 * 1024  # 20 MB


class PyrogramHandler:
    """Wraps a Pyrogram user client for unlimited-size file downloads."""

    def __init__(self, api_id: int, api_hash: str, phone: str, bot_id: int, downloads_dir: Path):
        self.api_id = api_id
        self.api_hash = api_hash
        self.phone = phone
        self.bot_id = bot_id
        self.downloads_dir = Path(downloads_dir)
        self.client: Optional["Client"] = None
        self._started = False
        self._me_name = "User"

        # Context registered by Bot API handler: file_unique_id → dict
        self._contexts: Dict[str, Any] = {}

        # Dashboard broadcast callbacks (set in start())
        self._broadcast_progress: Optional[Callable] = None
        self._broadcast_file_received: Optional[Callable] = None

    # ── Public API used by Bot API handler ────────────────────────────────

    def register_context(
        self,
        file_unique_id: str,
        username: str,
        file_type: str,
        original_name: str,
        status_message,          # telegram.Message — for editing progress in chat
    ):
        """Register metadata so Pyrogram can edit the correct bot message."""
        self._contexts[file_unique_id] = {
            "username": username,
            "file_type": file_type,
            "original_name": original_name,
            "status_message": status_message,
        }

    # ── Lifecycle ─────────────────────────────────────────────────────────

    async def start(
        self,
        broadcast_progress: Optional[Callable] = None,
        broadcast_file_received: Optional[Callable] = None,
    ):
        """Start the Pyrogram client and register the outgoing media handler."""
        if not _pyrogram_available:
            logger.error("pyrogram is not installed")
            return

        self._broadcast_progress = broadcast_progress
        self._broadcast_file_received = broadcast_file_received

        self.client = Client(
            name="pyrogram_session",
            api_id=self.api_id,
            api_hash=self.api_hash,
            phone_number=self.phone,
            workdir=str(Path(".").resolve()),
        )

        _handler = self  # capture self for nested async def

        @self.client.on_message(filters.outgoing & filters.chat(self.bot_id))
        async def _outgoing_media(client, message):
            await _handler._handle_outgoing_media(client, message)

        await self.client.start()
        self._started = True
        me = await self.client.get_me()
        self._me_name = me.first_name or "User"
        logger.info(f"Pyrogram logged in as: {me.first_name} (@{me.username})")

    async def stop(self):
        """Stop the Pyrogram client."""
        if self.client and self._started:
            await self.client.stop()
            self._started = False

    @property
    def is_ready(self) -> bool:
        return self._started and self.client is not None

    # ── Internal download logic ───────────────────────────────────────────

    async def _handle_outgoing_media(self, client, message):
        """Download an outgoing large-file message and notify the dashboard."""
        media = (
            message.document
            or message.video
            or message.audio
            or message.voice
            or message.photo
        )
        if not media:
            logger.debug(f"Pyrogram: outgoing non-media msg {message.id} — skipping")
            return

        file_size = getattr(media, "file_size", 0) or 0
        file_unique_id = getattr(media, "file_unique_id", f"msg_{message.id}")
        logger.info(f"Pyrogram: outgoing media msg={message.id} "
                    f"unique={file_unique_id} size={file_size/1048576:.1f} MB")

        # Skip small files — the Bot API already handles them
        if 0 < file_size <= MAX_BOT_FILE_SIZE:
            logger.info(f"Pyrogram: file is small ({file_size} B) — leaving to Bot API")
            return

        # Retrieve context registered by the Bot API handler (may be None if
        # Pyrogram fired faster than the Bot API processed the message).
        # We retry a few times to handle the race condition.
        ctx = None
        for _ in range(5):
            ctx = self._contexts.pop(file_unique_id, None)
            if ctx:
                break
            await asyncio.sleep(0.5)
            
        logger.info(f"Pyrogram: ctx found={ctx is not None} for {file_unique_id}")

        original_name = (
            (ctx["original_name"] if ctx else None)
            or getattr(media, "file_name", None)
            or f"file_{message.id}"
        )
        username  = ctx["username"]  if ctx else self._me_name
        file_type = ctx["file_type"] if ctx else "document"

        # Ensure save path won't overwrite existing files
        save_path = self.downloads_dir / original_name
        if save_path.exists():
            stem   = Path(original_name).stem
            suffix = Path(original_name).suffix
            save_path    = self.downloads_dir / f"{stem}_{message.id}{suffix}"
            original_name = save_path.name

        logger.info(f"Pyrogram downloading → {save_path}")

        last_pct = [-1]

        async def _progress(current, total):
            pct = int(current * 100 / total) if total > 0 else 0
            if pct - last_pct[0] < 5:
                return
            last_pct[0] = pct
            logger.info(f"Pyrogram progress {pct}%: {original_name} "
                         f"({current//1048576}/{total//1048576} MB)")

            # Edit the bot's status message in Telegram
            if ctx and ctx.get("status_message"):
                bar = "█" * (pct // 10) + "░" * (10 - pct // 10)
                try:
                    await ctx["status_message"].edit_text(
                        f"⏳ Downloading: [{bar}] {pct}%\n`{original_name}`",
                        parse_mode="Markdown",
                    )
                except Exception:
                    pass


            # Push to dashboard
            if self._broadcast_progress:
                try:
                    await self._broadcast_progress(
                        filename=original_name,
                        current_bytes=current,
                        total_bytes=total,
                        pct=pct,
                    )
                except Exception as e:
                    logger.error(f"Pyrogram: broadcast_progress error: {e}")
            else:
                logger.warning("Pyrogram: _broadcast_progress is None — no dashboard update")

        try:
            logger.info(f"Pyrogram: starting download_media → {save_path}")
            await client.download_media(
                message, file_name=str(save_path), progress=_progress
            )
            logger.info(f"Pyrogram: download_media returned for {save_path}")

            if not save_path.exists():
                raise FileNotFoundError(f"Downloaded file missing: {save_path}")

            full_size = save_path.stat().st_size
            logger.info(f"Pyrogram download complete: {save_path} "
                        f"({full_size / 1048576:.1f} MB)")

            # Final dashboard update (100 % + done)
            if self._broadcast_progress:
                try:
                    await self._broadcast_progress(
                        filename=original_name,
                        current_bytes=full_size,
                        total_bytes=full_size,
                        pct=100,
                        done=True,
                    )
                except Exception as e:
                    logger.error(f"Pyrogram: final broadcast_progress failed: {e}")
            if self._broadcast_file_received:
                try:
                    await self._broadcast_file_received(
                        username=username,
                        filename=original_name,
                        file_type=file_type,
                        file_size=full_size,
                    )
                except Exception as e:
                    logger.error(f"Pyrogram: broadcast_file_received failed: {e}")
            else:
                logger.warning("Pyrogram: _broadcast_file_received is None")

            # Update or send completion message in Telegram chat
            if ctx and ctx.get("status_message"):
                await ctx["status_message"].edit_text(
                    f"✅ *Downloaded:* `{original_name}`\n"
                    f"Size: {full_size / 1048576:.1f} MB",
                    parse_mode="Markdown",
                )
            else:
                await client.send_message(
                    self.bot_id,
                    f"✅ Downloaded: `{original_name}` "
                    f"({full_size / 1048576:.1f} MB)",
                )

        except FloodWait as e:
            logger.warning(f"Pyrogram FloodWait: sleeping {e.value}s")
            await asyncio.sleep(e.value)
            if ctx and ctx.get("status_message"):
                try:
                    await ctx["status_message"].edit_text("⚠️ Rate limited — please retry.")
                except Exception:
                    pass

        except Exception as e:
            logger.error(f"Pyrogram download error: {e}")
            if self._broadcast_progress:
                try:
                    await self._broadcast_progress(
                        filename=original_name,
                        current_bytes=0, total_bytes=0, pct=0, done=True,
                    )
                except Exception:
                    pass
            if ctx and ctx.get("status_message"):
                try:
                    await ctx["status_message"].edit_text(
                        "❌ Download failed. Check server logs."
                    )
                except Exception:
                    pass


def create_pyrogram_handler(
    bot_token: str,
    downloads_dir: Path,
) -> Optional["PyrogramHandler"]:
    """Factory — returns a PyrogramHandler if all env vars are set, else None."""
    if not _pyrogram_available:
        return None

    api_id_str = os.getenv("PYROGRAM_API_ID", "")
    api_hash   = os.getenv("PYROGRAM_API_HASH", "")
    phone      = os.getenv("PYROGRAM_PHONE", "")

    if not api_id_str or not api_hash or not phone:
        logger.info(
            "PYROGRAM_API_ID / PYROGRAM_API_HASH / PYROGRAM_PHONE not set — "
            "running in Bot-API-only mode (20 MB limit applies)"
        )
        return None

    try:
        api_id = int(api_id_str)
    except ValueError:
        logger.error("PYROGRAM_API_ID must be an integer")
        return None

    try:
        bot_id = int(bot_token.split(":")[0])
    except (ValueError, IndexError):
        logger.error("Could not extract bot_id from TELEGRAM_BOT_TOKEN")
        return None

    return PyrogramHandler(api_id, api_hash, phone, bot_id, downloads_dir)
