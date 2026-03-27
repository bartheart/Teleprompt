"""
Tests for Socket.IO session lifecycle handlers: connect, disconnect, start_session.
"""

import sys
import types
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

if "faster_whisper" not in sys.modules:
    fw = types.ModuleType("faster_whisper")
    fw.WhisperModel = object  # type: ignore[attr-defined]
    sys.modules["faster_whisper"] = fw

from routes.routes import (
    DEFAULT_PREDICTION_COUNT,
    SessionState,
    connect,
    disconnect,
    sessions,
    start_session,
)


# ---------------------------------------------------------------------------
# connect
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_connect_creates_session():
    sid = "connect-test-001"
    sessions.pop(sid, None)

    with patch("routes.routes.sio") as mock_sio:
        mock_sio.emit = AsyncMock()
        await connect(sid, {})

    assert sid in sessions
    assert isinstance(sessions[sid], SessionState)
    sessions.pop(sid, None)


@pytest.mark.asyncio
async def test_connect_emits_connect_response():
    sid = "connect-test-002"
    sessions.pop(sid, None)

    with patch("routes.routes.sio") as mock_sio:
        mock_sio.emit = AsyncMock()
        await connect(sid, {})
        call_args = mock_sio.emit.call_args
        assert call_args.args[0] == "connect_response"
        assert call_args.args[1]["status"] == "connected"
        assert "prediction_model" in call_args.args[1]

    sessions.pop(sid, None)


# ---------------------------------------------------------------------------
# disconnect
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_disconnect_removes_session():
    sid = "disconnect-test-001"
    sessions[sid] = SessionState()

    await disconnect(sid)

    assert sid not in sessions


@pytest.mark.asyncio
async def test_disconnect_unknown_sid_is_safe():
    # Should not raise even if sid was never registered
    await disconnect("nonexistent-sid-xyz")


# ---------------------------------------------------------------------------
# start_session
# ---------------------------------------------------------------------------

@pytest.fixture
def fresh_session():
    sid = "session-test-001"
    sessions[sid] = SessionState()
    yield sid
    sessions.pop(sid, None)


@pytest.mark.asyncio
async def test_start_session_sets_context(fresh_session):
    await start_session(fresh_session, {"context": "machine learning talk", "predictionCount": 5})
    assert sessions[fresh_session].context == "machine learning talk"


@pytest.mark.asyncio
async def test_start_session_sets_prediction_count(fresh_session):
    await start_session(fresh_session, {"context": "", "predictionCount": 7})
    assert sessions[fresh_session].prediction_count == 7


@pytest.mark.asyncio
async def test_start_session_clears_transcript(fresh_session):
    sessions[fresh_session].full_transcript = "previous text"
    await start_session(fresh_session, {"context": "new context", "predictionCount": 5})
    assert sessions[fresh_session].full_transcript == ""


@pytest.mark.asyncio
async def test_start_session_clamps_prediction_count_min(fresh_session):
    await start_session(fresh_session, {"context": "", "predictionCount": 0})
    assert sessions[fresh_session].prediction_count == 1


@pytest.mark.asyncio
async def test_start_session_clamps_prediction_count_max(fresh_session):
    await start_session(fresh_session, {"context": "", "predictionCount": 99})
    assert sessions[fresh_session].prediction_count == 10


@pytest.mark.asyncio
async def test_start_session_invalid_prediction_count_uses_default(fresh_session):
    await start_session(fresh_session, {"context": "", "predictionCount": "bad"})
    assert sessions[fresh_session].prediction_count == DEFAULT_PREDICTION_COUNT


@pytest.mark.asyncio
async def test_start_session_missing_payload_is_safe(fresh_session):
    await start_session(fresh_session, {})
    assert sessions[fresh_session].context == ""
    assert sessions[fresh_session].prediction_count == DEFAULT_PREDICTION_COUNT


@pytest.mark.asyncio
async def test_start_session_unknown_sid_is_safe():
    # Should not raise for unregistered session
    await start_session("nonexistent-sid-xyz", {"context": "test", "predictionCount": 5})


@pytest.mark.asyncio
async def test_start_session_trims_context_whitespace(fresh_session):
    await start_session(fresh_session, {"context": "  trimmed  ", "predictionCount": 5})
    assert sessions[fresh_session].context == "trimmed"


# ---------------------------------------------------------------------------
# connect_response includes prediction_model
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_connect_response_includes_model_claude():
    """connect_response has prediction_model=claude-haiku when client is initialised."""
    import routes.routes as routes_module
    sid = "model-test-claude"
    sessions.pop(sid, None)

    captured = {}
    async def capture_emit(event, data, **_):
        captured[event] = data

    with (
        patch.object(routes_module, "_anthropic_client", MagicMock()),
        patch("routes.routes.sio") as mock_sio,
    ):
        mock_sio.emit = capture_emit
        await connect(sid, {})

    assert captured["connect_response"]["prediction_model"] == "claude-haiku"
    sessions.pop(sid, None)


@pytest.mark.asyncio
async def test_connect_response_includes_model_basic():
    """connect_response has prediction_model=basic when client is None (no key)."""
    import routes.routes as routes_module
    sid = "model-test-basic"
    sessions.pop(sid, None)

    captured = {}
    async def capture_emit(event, data, **_):
        captured[event] = data

    with (
        patch.object(routes_module, "_anthropic_client", None),
        patch("routes.routes.sio") as mock_sio,
    ):
        mock_sio.emit = capture_emit
        await connect(sid, {})

    assert captured["connect_response"]["prediction_model"] == "basic"
    sessions.pop(sid, None)
