"""
Telegram Bot - Handles polling and command processing
"""
import asyncio
import os
import logging
from pathlib import Path
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from websocket_manager import ws_manager

logger = logging.getLogger(__name__)

# Default — overridden at construction time by main.py
DOWNLOADS_DIR = Path("downloads")
DOWNLOADS_DIR.mkdir(exist_ok=True)


class TelegramBot:
    def __init__(self, token: str, allowed_chat_ids: list = None, pyrogram_handler=None, downloads_dir: Path = None):
        self.token = token
        self.allowed_chat_ids = allowed_chat_ids
        self.pyrogram_handler = pyrogram_handler
        self.downloads_dir = downloads_dir or Path("downloads")
        self.downloads_dir.mkdir(parents=True, exist_ok=True)
        self.application = None
        
    def is_authorized(self, chat_id: int) -> bool:
        """Check if chat_id is authorized"""
        if not self.allowed_chat_ids:
            return True
        return chat_id in self.allowed_chat_ids
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command"""
        chat_id = update.effective_chat.id
        username = update.effective_user.username or update.effective_user.first_name
        
        if not self.is_authorized(chat_id):
            await update.message.reply_text("Sorry, you are not authorized to use this bot.")
            return
        
        welcome_message = (
            "🤖 *Welcome to Telegram Dashboard Bot!*\n\n"
            "I can receive your files and display activity on a live dashboard.\n\n"
            "*Commands:*\n"
            "/start - Show this message\n"
            "/help - Show help information\n\n"
            "*Send Files:*\n"
            "Send any document, photo, video, audio or voice message to download it to the server."
        )
        
        await update.message.reply_text(welcome_message, parse_mode='Markdown')
        await ws_manager.broadcast_status("bot_command", f"User {username} started the bot")
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command"""
        chat_id = update.effective_chat.id
        
        if not self.is_authorized(chat_id):
            await update.message.reply_text("Sorry, you are not authorized to use this bot.")
            return
        
        help_message = (
            "📚 *Help - Telegram Dashboard Bot*\n\n"
            "*How to use:*\n"
            "1. Send any file (document, photo, video, audio, voice) and the bot will save it to the server.\n"
            "2. You can download files from the dashboard at `/downloads`.\n\n"
            "*Status Updates:*\n"
            "You'll receive a confirmation message when your file is saved."
        )
        
        await update.message.reply_text(help_message, parse_mode='Markdown')
    
    async def handle_file(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle incoming files (documents, photos, videos, audio, voice)"""
        chat_id = update.effective_chat.id
        username = update.effective_user.username or update.effective_user.first_name

        if not self.is_authorized(chat_id):
            await update.message.reply_text("Sorry, you are not authorized to use this bot.")
            return

        msg = update.message

        # Telegram Bot API limit: bots can only download files up to 20 MB
        MAX_FILE_SIZE = 20 * 1024 * 1024  # 20 MB in bytes

        # Determine file type and extract metadata (without downloading yet)
        if msg.document:
            original_name = msg.document.file_name or f"document_{msg.document.file_unique_id}"
            file_type = "document"
            file_size = msg.document.file_size or 0
            tg_obj = msg.document
        elif msg.photo:
            photo = msg.photo[-1]
            original_name = f"photo_{photo.file_unique_id}.jpg"
            file_type = "photo"
            file_size = photo.file_size or 0
            tg_obj = photo
        elif msg.video:
            original_name = msg.video.file_name or f"video_{msg.video.file_unique_id}.mp4"
            file_type = "video"
            file_size = msg.video.file_size or 0
            tg_obj = msg.video
        elif msg.audio:
            original_name = msg.audio.file_name or f"audio_{msg.audio.file_unique_id}.mp3"
            file_type = "audio"
            file_size = msg.audio.file_size or 0
            tg_obj = msg.audio
        elif msg.voice:
            original_name = f"voice_{msg.voice.file_unique_id}.ogg"
            file_type = "voice"
            file_size = msg.voice.file_size or 0
            tg_obj = msg.voice
        else:
            await update.message.reply_text("Unsupported file type.")
            return

        # Reject files larger than 20 MB (Telegram Bot API hard limit)
        if file_size > MAX_FILE_SIZE:
            size_mb = file_size / (1024 * 1024)

            # If Pyrogram is available, use it for large files
            if self.pyrogram_handler and self.pyrogram_handler.is_ready:
                sent = await update.message.reply_text(
                    f"⏳ *Large file detected* ({size_mb:.1f} MB)\n"
                    f"Downloading via Pyrogram… this may take a while.",
                    parse_mode='Markdown'
                )
                # Register context so Pyrogram knows which message to edit and
                # what filename/username to associate with the download.
                self.pyrogram_handler.register_context(
                    file_unique_id=tg_obj.file_unique_id,
                    username=username,
                    file_type=file_type,
                    original_name=original_name,
                    status_message=sent,
                )
                return  # Pyrogram's outgoing-media handler takes it from here
            else:
                # Pyrogram not configured — inform user
                await update.message.reply_text(
                    f"⚠️ *File too large* ({size_mb:.1f} MB)\n\n"
                    f"Telegram bots can only download files up to 20 MB.\n"
                    f"To enable large file support, configure Pyrogram credentials in `.env`.",
                    parse_mode='Markdown'
                )
                return

        # Now safe to download
        tg_file = await tg_obj.get_file()

        # Save to downloads directory
        save_path = self.downloads_dir / original_name
        # Avoid overwriting by appending unique ID if name already exists
        if save_path.exists():
            stem = Path(original_name).stem
            suffix = Path(original_name).suffix
            save_path = self.downloads_dir / f"{stem}_{tg_file.file_unique_id}{suffix}"
            original_name = save_path.name

        await tg_file.download_to_drive(str(save_path))
        logger.info(f"File saved: {save_path}")

        # Broadcast to dashboard
        await ws_manager.broadcast_file_received(
            username=username,
            filename=original_name,
            file_type=file_type,
            file_size=file_size or 0,
        )

        await update.message.reply_text(
            f"✅ *File saved:* `{original_name}`\n"
            f"You can download it from the dashboard.",
            parse_mode='Markdown'
        )

    async def unknown_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle unknown commands"""
        await update.message.reply_text(
            "Unknown command. Use /help to see available commands."
        )
    
    async def start_polling(self):
        """Start the Telegram bot polling"""
        try:
            # Create application
            self.application = Application.builder().token(self.token).build()
            
            # Add handlers
            self.application.add_handler(CommandHandler("start", self.start_command))
            self.application.add_handler(CommandHandler("help", self.help_command))
            # File handler — catches documents, photos, video, audio, voice
            file_filter = (
                filters.Document.ALL
                | filters.PHOTO
                | filters.VIDEO
                | filters.AUDIO
                | filters.VOICE
            )
            self.application.add_handler(MessageHandler(file_filter, self.handle_file))
            self.application.add_handler(MessageHandler(filters.COMMAND, self.unknown_command))
            
            # Start polling
            logger.info("Starting Telegram bot polling...")
            await ws_manager.broadcast_status("bot_started", "Telegram bot is now polling")
            
            await self.application.initialize()
            await self.application.start()
            await self.application.updater.start_polling(drop_pending_updates=True)
            
            logger.info("Telegram bot is running!")
            
        except Exception as e:
            logger.error(f"Error starting Telegram bot: {e}")
            await ws_manager.broadcast_error(f"Telegram bot error: {str(e)}")
    
    async def stop_polling(self):
        """Stop the Telegram bot polling"""
        if self.application:
            logger.info("Stopping Telegram bot...")
            await self.application.updater.stop()
            await self.application.stop()
            await self.application.shutdown()
            await ws_manager.broadcast_status("bot_stopped", "Telegram bot polling stopped")
