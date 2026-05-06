"""SSE streaming and WebSocket integration tests."""

import asyncio
import json
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from fastapi.testclient import TestClient

from src.api.main import create_app
from src.services.auth import User
from src.engine.scheduler import EventEmitter, WorkflowEvent, WorkflowEventType


@pytest.fixture
def client():
    app = create_app()
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def mock_user():
    return User(
        user_id="u_test",
        email="test@example.com",
        workspace_id="ws_001",
        roles=["developer"],
        auth_method="api_key",
        key_id="key_001",
    )


@pytest.fixture
def auth_headers():
    return {"Authorization": "Bearer sk-test1234567890"}


# ---------------------------------------------------------------------------
# EventEmitter
# ---------------------------------------------------------------------------

class TestEventEmitter:

    @pytest.mark.asyncio
    async def test_subscribe_and_emit(self):
        emitter = EventEmitter()
        received = []

        async def handler(event: WorkflowEvent):
            received.append(event)

        emitter.subscribe(handler)

        event = WorkflowEvent(
            event_type=WorkflowEventType.WORKFLOW_STARTED,
            data={"execution_id": "e1", "workflow_id": "w1"},
        )
        await emitter.emit(event)

        assert len(received) == 1
        assert received[0].event_type == WorkflowEventType.WORKFLOW_STARTED
        assert received[0].data["execution_id"] == "e1"

    @pytest.mark.asyncio
    async def test_unsubscribe(self):
        emitter = EventEmitter()
        received = []

        async def handler(event: WorkflowEvent):
            received.append(event)

        emitter.subscribe(handler)
        emitter.unsubscribe(handler)

        event = WorkflowEvent(
            event_type=WorkflowEventType.WORKFLOW_STARTED,
            data={},
        )
        await emitter.emit(event)

        assert len(received) == 0

    @pytest.mark.asyncio
    async def test_multiple_subscribers(self):
        emitter = EventEmitter()
        received_a = []
        received_b = []

        async def handler_a(event):
            received_a.append(event)

        async def handler_b(event):
            received_b.append(event)

        emitter.subscribe(handler_a)
        emitter.subscribe(handler_b)

        await emitter.emit(WorkflowEvent(
            event_type=WorkflowEventType.NODE_STARTED,
            data={"node_id": "n1"},
        ))

        assert len(received_a) == 1
        assert len(received_b) == 1

    @pytest.mark.asyncio
    async def test_subscriber_error_does_not_break_others(self):
        emitter = EventEmitter()
        received = []

        async def bad_handler(event):
            raise RuntimeError("boom")

        async def good_handler(event):
            received.append(event)

        emitter.subscribe(bad_handler)
        emitter.subscribe(good_handler)

        await emitter.emit(WorkflowEvent(
            event_type=WorkflowEventType.PING,
            data={},
        ))

        assert len(received) == 1


# ---------------------------------------------------------------------------
# ConnectionManager
# ---------------------------------------------------------------------------

class TestConnectionManager:

    def test_create_and_remove_sse_queue(self):
        from src.api.routes.streaming import ConnectionManager

        mgr = ConnectionManager()
        q = mgr.create_sse_queue("exec_1", "conn_1")
        assert isinstance(q, asyncio.Queue)

        mgr.remove_sse_queue("exec_1", "conn_1")
        assert "exec_1" not in mgr._sse_queues or len(mgr._sse_queues.get("exec_1", {})) == 0

    @pytest.mark.asyncio
    async def test_broadcast_to_sse_queue(self):
        from src.api.routes.streaming import ConnectionManager

        mgr = ConnectionManager()
        q = mgr.create_sse_queue("exec_1", "conn_1")

        event = WorkflowEvent(
            event_type=WorkflowEventType.NODE_STARTED,
            data={"node_id": "n1"},
        )
        await mgr.broadcast("exec_1", event)

        message = await asyncio.wait_for(q.get(), timeout=1)
        parsed = json.loads(message)
        assert parsed["event"] == "node_started"
        assert parsed["data"]["node_id"] == "n1"

    @pytest.mark.asyncio
    async def test_broadcast_to_multiple_queues(self):
        from src.api.routes.streaming import ConnectionManager

        mgr = ConnectionManager()
        q1 = mgr.create_sse_queue("exec_1", "conn_1")
        q2 = mgr.create_sse_queue("exec_1", "conn_2")

        event = WorkflowEvent(
            event_type=WorkflowEventType.WORKFLOW_COMPLETED,
            data={"status": "succeeded"},
        )
        await mgr.broadcast("exec_1", event)

        msg1 = await asyncio.wait_for(q1.get(), timeout=1)
        msg2 = await asyncio.wait_for(q2.get(), timeout=1)
        assert json.loads(msg1)["event"] == "workflow_completed"
        assert json.loads(msg2)["event"] == "workflow_completed"


# ---------------------------------------------------------------------------
# SSE Endpoint
# ---------------------------------------------------------------------------

class TestSSEEndpoint:
    """SSE endpoint tests — skipped because TestClient blocks on StreamingResponse.

    These should be tested with httpx.AsyncClient or a separate thread.
    """

    @pytest.mark.skip(reason="StreamingResponse blocks TestClient — needs async client")
    def test_sse_stream_returns_event_stream_headers(self):
        pass

    @pytest.mark.skip(reason="StreamingResponse blocks TestClient — needs async client")
    def test_sse_endpoint_requires_auth(self):
        pass


# ---------------------------------------------------------------------------
# WebSocket Endpoint
# ---------------------------------------------------------------------------

class TestWebSocketEndpoint:

    @patch("src.services.auth.get_auth_service")
    def test_websocket_connect_and_subscribe(self, mock_get_auth, client, mock_user):
        mock_auth = MagicMock()
        mock_auth.validate_api_key.return_value = mock_user
        mock_get_auth.return_value = mock_auth

        with client.websocket_connect("/api/v1/ws/workflows/wf_1/executions/exec_1") as ws:
            # Should receive connected message
            data = ws.receive_json()
            assert data["event"] == "connected"
            assert "connection_id" in data["data"]

            # Send subscribe
            ws.send_json({"action": "subscribe"})
            data = ws.receive_json()
            assert data["event"] == "subscribed"

    @patch("src.services.auth.get_auth_service")
    def test_websocket_cancel(self, mock_get_auth, client, mock_user):
        mock_auth = MagicMock()
        mock_auth.validate_api_key.return_value = mock_user
        mock_get_auth.return_value = mock_auth

        with client.websocket_connect("/api/v1/ws/workflows/wf_1/executions/exec_1") as ws:
            ws.receive_json()  # connected

            ws.send_json({"action": "cancel"})
            data = ws.receive_json()
            assert data["event"] == "cancelled"

    @patch("src.services.auth.get_auth_service")
    def test_websocket_unknown_action(self, mock_get_auth, client, mock_user):
        mock_auth = MagicMock()
        mock_auth.validate_api_key.return_value = mock_user
        mock_get_auth.return_value = mock_auth

        with client.websocket_connect("/api/v1/ws/workflows/wf_1/executions/exec_1") as ws:
            ws.receive_json()  # connected

            ws.send_json({"action": "invalid"})
            data = ws.receive_json()
            assert data["event"] == "error"


# ---------------------------------------------------------------------------
# LLM Streaming Integration
# ---------------------------------------------------------------------------

class TestLLMStreaming:

    @pytest.mark.asyncio
    async def test_llm_node_emits_streaming_events(self):
        """LLMNode should emit NODE_STREAMING events when event_emitter is present."""
        from src.nodes.ai.nodes import LLMNode
        from src.engine.abstractions import ExecutionContext, NodeStatus

        emitter = EventEmitter()
        received_events = []

        async def handler(event):
            received_events.append(event)

        emitter.subscribe(handler)

        context = ExecutionContext(
            execution_id="exec_test",
            workflow_id="wf_test",
            workflow_version="1.0",
            user_id="u_test",
            environment="test",
            event_emitter=emitter,
        )

        # Mock the variable pool
        pool = MagicMock()
        pool.get.return_value = "Hello, world!"
        pool.resolve_template.return_value = "Hello, world!"

        # Mock ModelRouter.call_llm_stream
        from src.services.model_router import StreamingChunk

        async def mock_stream(*args, **kwargs):
            yield StreamingChunk(text="Hello, ")
            yield StreamingChunk(text="world!")
            yield StreamingChunk(text="", is_final=True)

        node = LLMNode.__new__(LLMNode)
        node.node_id = "llm_1"
        node.node_config = {"model": "gpt-4o", "stream": True}

        with patch("src.nodes.ai.nodes.ModelRouter") as MockRouter:
            router_instance = MagicMock()
            router_instance.call_llm_stream = mock_stream
            MockRouter.return_value = router_instance

            result = await node.execute(pool, context)

        assert result.status == NodeStatus.SUCCEEDED
        assert result.outputs["text"] == "Hello, world!"

        # Should have emitted NODE_STREAMING events
        streaming_events = [e for e in received_events if e.event_type == WorkflowEventType.NODE_STREAMING]
        assert len(streaming_events) >= 2
        assert streaming_events[0].data["chunk"] == "Hello, "
        assert streaming_events[1].data["chunk"] == "world!"

    @pytest.mark.asyncio
    async def test_llm_node_falls_back_to_sync_without_emitter(self):
        """LLMNode should use non-streaming path when no event_emitter."""
        from src.nodes.ai.nodes import LLMNode
        from src.engine.abstractions import ExecutionContext, NodeStatus

        context = ExecutionContext(
            execution_id="exec_test",
            workflow_id="wf_test",
            workflow_version="1.0",
            user_id="u_test",
            environment="test",
        )

        pool = MagicMock()
        pool.get.return_value = "Hello"
        pool.resolve_template.return_value = "Hello"

        node = LLMNode.__new__(LLMNode)
        node.node_id = "llm_1"
        node.node_config = {"model": "gpt-4o", "stream": True}

        with patch("src.nodes.ai.nodes.ModelRouter") as MockRouter:
            router_instance = MagicMock()
            router_instance.call_llm = AsyncMock(return_value={
                "content": "Hi there",
                "usage": {"total_tokens": 10},
                "finish_reason": "stop",
            })
            MockRouter.return_value = router_instance

            result = await node.execute(pool, context)

        assert result.status == NodeStatus.SUCCEEDED
        assert result.outputs["text"] == "Hi there"
