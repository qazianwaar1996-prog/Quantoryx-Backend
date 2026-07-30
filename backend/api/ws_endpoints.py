# backend/api/ws_endpoints.py
"""
Quantoryx — Real-Time WebSocket Streaming Router Module.

Implements a centralized WebSocket connection manager with user-scoped connection mapping.
Enforces JWT authorization during websocket handshakes to secure high-frequency stream channels.
"""

from typing import Dict, List, Any, Optional
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query, status

# Core security and path resolutions
from backend.services.security_service import SecurityService
from utils.logging_config import get_logger

logger = get_logger("backend.api.ws_endpoints")

# Initialize Router
router = APIRouter(prefix="/api/ws", tags=["Real-Time WebSockets"])


class ConnectionManager:
    """
    Manages active WebSocket connections mapped by User UUID keys to enforce
    security boundaries and prevent broadcast leaking.
    """
    def __init__(self):
        # Map user_id (str) -> list of active WebSocket connections
        self.active_connections: Dict[str, List[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, user_id: str):
        """Accepts a WebSocket connection and registers it under the user's scope."""
        await websocket.accept()
        if user_id not in self.active_connections:
            self.active_connections[user_id] = []
        self.active_connections[user_id].append(websocket)
        logger.info("WebSocket connected for User %s. Active connections: %s", user_id, len(self.active_connections[user_id]))

    def disconnect(self, websocket: WebSocket, user_id: str):
        """Unregisters a closed WebSocket connection."""
        if user_id in self.active_connections:
            if websocket in self.active_connections[user_id]:
                self.active_connections[user_id].remove(websocket)
            if not self.active_connections[user_id]:
                del self.active_connections[user_id]
        logger.info("WebSocket disconnected for User %s.", user_id)

    async def send_personal_message(self, message: Any, websocket: WebSocket):
        """Sends a JSON payload directly to a specific socket connection."""
        await websocket.send_json(message)

    async def send_to_user(self, user_id: str, message: Any):
        """Broadcasts a JSON payload to all active connections belonging to a single user."""
        if user_id in self.active_connections:
            for connection in self.active_connections[user_id]:
                try:
                    await connection.send_json(message)
                except Exception as e:
                    logger.debug("Failed to send message to user connection %s: %s", user_id, str(e))

    async def broadcast(self, message: Any):
        """Broadcasts a JSON payload globally to all connected active user channels."""
        for user_id, connections in self.active_connections.items():
            for connection in connections:
                try:
                    await connection.send_json(message)
                except Exception as e:
                    logger.debug("Failed global broadcast to user %s: %s", user_id, str(e))


# Instantiate singleton manager for global import access
manager = ConnectionManager()


@router.websocket("/{user_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    user_id: str,
    token: Optional[str] = Query(None, description="Signed JWT authorization token")
):
    """
    WebSocket endpoint establishing an active duplex channel.
    Parses and verifies token signature before accepting the socket connection.
    """
    if not token:
        logger.warning("WebSocket handshake rejected: Token query parameter is missing.")
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    # Verify authorization JWT token
    claims = SecurityService.verify_token(token, expected_type="access")
    if not claims or claims.get("sub") != user_id:
        logger.warning("WebSocket handshake rejected: Token validation or User UUID mismatch for user: %s", user_id)
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    # Accept and register connection
    await manager.connect(websocket, user_id)

    try:
        while True:
            # Keep-alive loop and receiver for clients sending messages/subscriptions
            data = await websocket.receive_text()
            
            # Simple heartbeat response
            if data == "ping":
                await manager.send_personal_message({"type": "PONG", "timestamp": datetime.utcnow().isoformat()}, websocket)
            else:
                await manager.send_personal_message({"type": "ECHO", "received": data}, websocket)

    except WebSocketDisconnect:
        manager.disconnect(websocket, user_id)
    except Exception as e:
        logger.error("WebSocket runtime exception triggered: %s", str(e))
        manager.disconnect(websocket, user_id)
