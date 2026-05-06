"""SSE streaming and WebSocket real-time communication endpoints."""

import asyncio
import json
import time
import uuid
from typing import Any

import structlog
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from src.api.dependencies import CurrentUser, success_response
from src.engine.scheduler import EventEmitter, WorkflowEvent, WorkflowEventType

logger = structlog.get_logger()

router = APIRouter(tags=["Streaming"])


# ── Connection Manager ──


class ConnectionManager:
    """Manages WebSocket and SSE connections per execution."""

    def __init__(self, max_connections_per_user: int = 10) -> None:
        self._ws_connections: dict[str, dict[str, WebSocket]] = {}  # execution_id -> {conn_id: ws}
        self._sse_queues: dict[str, dict[str, asyncio.Queue]] = {}  # execution_id -> {conn_id: queue}
        self._max_per_user = max_connections_per_user

    async def connect_ws(self, execution_id: str, conn_id: str, ws: WebSocket) -> None:
        await ws.accept()
        if execution_id not in self._ws_connections:
            self._ws_connections[execution_id] = {}
        self._ws_connections[execution_id][conn_id] = ws

    def disconnect_ws(self, execution_id: str, conn_id: str) -> None:
        if execution_id in self._ws_connections:
            self._ws_connections[execution_id].pop(conn_id, None)
            if not self._ws_connections[execution_id]:
                del self._ws_connections[execution_id]

    def create_sse_queue(self, execution_id: str, conn_id: str) -> asyncio.Queue:
        if execution_id not in self._sse_queues:
            self._sse_queues[execution_id] = {}
        queue: asyncio.Queue = asyncio.Queue()
        self._sse_queues[execution_id][conn_id] = queue
        return queue

    def remove_sse_queue(self, execution_id: str, conn_id: str) -> None:
        if execution_id in self._sse_queues:
            self._sse_queues[execution_id].pop(conn_id, None)
            if not self._sse_queues[execution_id]:
                del self._sse_queues[execution_id]

    async def broadcast(self, execution_id: str, event: WorkflowEvent) -> None:
        """Broadcast an event to all connections for an execution."""
        message = json.dumps({"event": event.event_type.value, "data": event.data, "timestamp": event.timestamp})

        # WebSocket connections
        for conn_id, ws in list(self._ws_connections.get(execution_id, {}).items()):
            try:
                await ws.send_text(message)
            except Exception:
                self.disconnect_ws(execution_id, conn_id)

        # SSE queues
        for conn_id, queue in list(self._sse_queues.get(execution_id, {}).items()):
            try:
                await queue.put(message)
            except Exception:
                self.remove_sse_queue(execution_id, conn_id)


# Global connection manager
connection_manager = ConnectionManager()


# ── SSE Endpoint ──


@router.post("/workflows/{workflow_id}/executions/{execution_id}/stream")
async def start_sse_stream(workflow_id: str, execution_id: str, current_user: CurrentUser):
    """Start an SSE stream for a workflow execution.

    Returns a streaming response with Server-Sent Events.
    """
    conn_id = f"sse_{uuid.uuid4().hex[:8]}"
    queue = connection_manager.create_sse_queue(execution_id, conn_id)

    async def event_generator():
        try:
            # Send initial connection event
            yield f"event: connected\ndata: {json.dumps({'connection_id': conn_id})}\n\n"

            while True:
                try:
                    message = await asyncio.wait_for(queue.get(), timeout=30)
                    yield f"data: {message}\n\n"
                except asyncio.TimeoutError:
                    # Send heartbeat
                    yield f"event: ping\ndata: {json.dumps({'timestamp': time.time()})}\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            connection_manager.remove_sse_queue(execution_id, conn_id)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ── WebSocket Endpoint ──


@router.websocket("/ws/workflows/{workflow_id}/executions/{execution_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    workflow_id: str,
    execution_id: str,
):
    """WebSocket endpoint for real-time workflow execution updates.

    Protocol:
    - Client -> Server: {"action": "subscribe"} or {"action": "cancel"}
    - Server -> Client: {"event": "node_started", "data": {...}} etc.
    """
    conn_id = f"ws_{uuid.uuid4().hex[:8]}"

    await connection_manager.connect_ws(execution_id, conn_id, websocket)
    logger.info("WebSocket connected", execution_id=execution_id, conn_id=conn_id)

    try:
        # Send welcome message
        await websocket.send_json({
            "event": "connected",
            "data": {"connection_id": conn_id, "execution_id": execution_id},
        })

        while True:
            data = await websocket.receive_json()
            action = data.get("action")

            if action == "subscribe":
                await websocket.send_json({
                    "event": "subscribed",
                    "data": {"execution_id": execution_id},
                })
            elif action == "cancel":
                # TODO: cancel execution
                await websocket.send_json({
                    "event": "cancelled",
                    "data": {"execution_id": execution_id},
                })
                break
            else:
                await websocket.send_json({
                    "event": "error",
                    "data": {"message": f"Unknown action: {action}"},
                })

    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error("WebSocket error", error=str(e))
    finally:
        connection_manager.disconnect_ws(execution_id, conn_id)
        logger.info("WebSocket disconnected", execution_id=execution_id, conn_id=conn_id)
