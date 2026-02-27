"""
WebSocket Manager - Handles real-time communication with dashboard
"""
import asyncio
import json
from typing import Set, Dict, Any
from fastapi import WebSocket
import logging

logger = logging.getLogger(__name__)


class WebSocketManager:
    def __init__(self):
        self.active_connections: Set[WebSocket] = set()
        
    async def connect(self, websocket: WebSocket):
        """Accept and store new WebSocket connection"""
        await websocket.accept()
        self.active_connections.add(websocket)
        logger.info(f"WebSocket connected. Total connections: {len(self.active_connections)}")
        
        # Send welcome message
        await self.send_to_client(websocket, {
            "type": "system",
            "message": "Connected to Telegram Dashboard",
            "timestamp": asyncio.get_event_loop().time()
        })
    
    def disconnect(self, websocket: WebSocket):
        """Remove WebSocket connection"""
        self.active_connections.discard(websocket)
        logger.info(f"WebSocket disconnected. Total connections: {len(self.active_connections)}")
    
    async def send_to_client(self, websocket: WebSocket, data: Dict[str, Any]):
        """Send message to specific client"""
        try:
            await websocket.send_json(data)
        except Exception as e:
            logger.error(f"Error sending to client: {e}")
            self.disconnect(websocket)
    
    async def broadcast(self, data: Dict[str, Any]):
        """Broadcast message to all connected clients"""
        disconnected = set()
        for connection in self.active_connections:
            try:
                await connection.send_json(data)
            except Exception as e:
                logger.error(f"Error broadcasting to client: {e}")
                disconnected.add(connection)
        
        # Clean up disconnected clients
        for connection in disconnected:
            self.disconnect(connection)
    
    async def broadcast_telegram_command(self, chat_id: int, username: str, command: str):
        """Broadcast incoming Telegram command"""
        await self.broadcast({
            "type": "telegram_command",
            "chat_id": chat_id,
            "username": username,
            "command": command,
            "timestamp": asyncio.get_event_loop().time()
        })
    
    async def broadcast_status(self, status: str, details: str = ""):
        """Broadcast status update"""
        await self.broadcast({
            "type": "status",
            "status": status,
            "details": details,
            "timestamp": asyncio.get_event_loop().time()
        })
    
    async def broadcast_error(self, error: str):
        """Broadcast error message"""
        await self.broadcast({
            "type": "error",
            "error": error,
            "timestamp": asyncio.get_event_loop().time()
        })

    async def broadcast_file_received(self, username: str, filename: str, file_type: str, file_size: int):
        """Broadcast file received/downloaded event"""
        await self.broadcast({
            "type": "file_received",
            "username": username,
            "filename": filename,
            "file_type": file_type,
            "file_size": file_size,
            "timestamp": asyncio.get_event_loop().time()
        })

    async def broadcast_download_progress(
        self,
        filename: str,
        current_bytes: int,
        total_bytes: int,
        pct: int,
        done: bool = False,
    ):
        """Broadcast live download progress for a file"""
        await self.broadcast({
            "type": "download_progress",
            "filename": filename,
            "current_bytes": current_bytes,
            "total_bytes": total_bytes,
            "pct": pct,
            "done": done,
            "timestamp": asyncio.get_event_loop().time()
        })


# Global instance
ws_manager = WebSocketManager()
