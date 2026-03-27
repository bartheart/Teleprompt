"""
Tests for stream_llm_prediction() — Claude Haiku 3.5 streaming phrase completion.

Covers:
  1. Progressive streaming emits growing phrases to sio.emit
  2. Falls back to bigram when _anthropic_client is None (no API key)
  3. Falls back silently on API error
  4. Falls back on empty/whitespace stream response
  5. In-flight task is cancelled when a new transcription fires
"""

import asyncio
import sys
import types
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Stub faster_whisper so routes.py imports cleanly without the model installed
# ---------------------------------------------------------------------------
if "faster_whisper" not in sys.modules:
    fw = types.ModuleType("faster_whisper")
    fw.WhisperModel = MagicMock  # type: ignore[attr-defined]
    sys.modules["faster_whisper"] = fw

import routes.routes as routes_module
from routes.routes import SessionState, sessions, stream_llm_prediction


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_async_text_stream(tokens: list[str]):
    """Return an async iterator that yields the given token strings."""
    async def _gen():
        for t in tokens:
            yield t
    return _gen()


def make_stream_ctx(tokens: list[str]):
    """
    Build a mock async context manager that exposes a .text_stream async iterator,
    matching the anthropic SDK's `client.messages.stream(...)` interface.
    """
    @asynccontextmanager
    async def _ctx():
        mock_stream = MagicMock()
        mock_stream.text_stream = make_async_text_stream(tokens)
        yield mock_stream
    return _ctx()


@pytest.fixture
def sid():
    _sid = "llm-test-sid-001"
    sessions[_sid] = SessionState()
    yield _sid
    sessions.pop(_sid, None)


# ---------------------------------------------------------------------------
# 1. Progressive streaming emits growing phrases
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_streaming_emits_progressive_phrases(sid):
    tokens = ["think", " about", " the", " key", " points"]
    emitted = []

    async def capture(event, data, **_):
        if event == "predictions":
            emitted.append(data["items"][0])

    mock_client = MagicMock()
    mock_client.messages.stream = MagicMock(return_value=make_stream_ctx(tokens))

    with (
        patch.object(routes_module, "_anthropic_client", mock_client),
        patch("routes.routes.sio") as mock_sio,
    ):
        mock_sio.emit = capture
        await stream_llm_prediction(sid, "tech talk", "I want to")

    # Each emit should be a prefix of the next
    assert len(emitted) == len(tokens)
    assert emitted[0] == "think"
    assert emitted[-1] == "think about the key points"
    for i in range(1, len(emitted)):
        assert emitted[i].startswith(emitted[i - 1].rstrip())


# ---------------------------------------------------------------------------
# 2. Falls back to bigram when no API key (_anthropic_client is None)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_falls_back_when_no_api_key(sid):
    emitted = []

    async def capture(event, data, **_):
        if event == "predictions":
            emitted.append(data["items"])

    with (
        patch.object(routes_module, "_anthropic_client", None),
        patch("routes.routes.sio") as mock_sio,
    ):
        mock_sio.emit = capture
        await stream_llm_prediction(sid, "context", "some transcript words here")

    assert len(emitted) == 1
    assert isinstance(emitted[0], list)
    assert len(emitted[0]) > 0


# ---------------------------------------------------------------------------
# 3. Falls back silently on API error
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_falls_back_on_api_error(sid):
    emitted_events = []

    async def capture(event, data, **_):
        emitted_events.append(event)

    @asynccontextmanager
    async def raising_ctx():
        raise RuntimeError("connection refused")
        yield  # noqa: unreachable

    mock_client = MagicMock()
    mock_client.messages.stream = MagicMock(return_value=raising_ctx())

    with (
        patch.object(routes_module, "_anthropic_client", mock_client),
        patch("routes.routes.sio") as mock_sio,
    ):
        mock_sio.emit = capture
        # Must not raise
        await stream_llm_prediction(sid, "context", "some transcript")

    assert "predictions" in emitted_events


# ---------------------------------------------------------------------------
# 4. Falls back on empty/whitespace stream response
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_falls_back_on_empty_stream(sid):
    emitted = []

    async def capture(event, data, **_):
        if event == "predictions":
            emitted.append(data["items"])

    mock_client = MagicMock()
    # Stream yields only whitespace tokens
    mock_client.messages.stream = MagicMock(return_value=make_stream_ctx(["   ", "  "]))

    with (
        patch.object(routes_module, "_anthropic_client", mock_client),
        patch("routes.routes.sio") as mock_sio,
    ):
        mock_sio.emit = capture
        await stream_llm_prediction(sid, "context", "some transcript words here")

    # Bigram fallback should have fired
    assert len(emitted) >= 1
    assert len(emitted[-1]) > 0


# ---------------------------------------------------------------------------
# 5. In-flight task is cancelled when a new transcription fires
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_previous_prediction_task_cancelled_on_new_transcription(sid):
    from routes.routes import audio_pcm
    import math
    import numpy as np

    SAMPLE_RATE = 16000

    def speech_pcm(n: int = 9000) -> bytes:
        t = np.linspace(0, n / SAMPLE_RATE, n, endpoint=False)
        samples = (np.sin(2 * math.pi * 440 * t) * 0.5).astype(np.float32)
        return (samples * 32767).astype(np.int16).tobytes()

    # Slow stream that won't finish before second audio_pcm call
    async def slow_text_stream():
        await asyncio.sleep(10)  # effectively never finishes in test
        yield "word"

    @asynccontextmanager
    async def slow_ctx():
        mock_stream = MagicMock()
        mock_stream.text_stream = slow_text_stream()
        yield mock_stream

    mock_client = MagicMock()
    mock_client.messages.stream = MagicMock(return_value=slow_ctx())

    fake_segment = MagicMock()
    fake_segment.text = "hello world"
    mock_model = MagicMock()
    mock_model.transcribe = MagicMock(return_value=([fake_segment], MagicMock()))

    with (
        patch.object(routes_module, "_anthropic_client", mock_client),
        patch("routes.routes.get_model", new=AsyncMock(return_value=mock_model)),
        patch("routes.routes.sio") as mock_sio,
    ):
        mock_sio.emit = AsyncMock()

        # First audio chunk — starts a prediction task
        await audio_pcm(sid, speech_pcm())
        first_task = sessions[sid].prediction_task
        assert first_task is not None

        # Second audio chunk — should cancel the first task
        await audio_pcm(sid, speech_pcm())
        second_task = sessions[sid].prediction_task

        # Give the event loop a tick to process cancellation
        await asyncio.sleep(0)

        assert first_task.cancelled() or first_task.done()
        assert second_task is not first_task
