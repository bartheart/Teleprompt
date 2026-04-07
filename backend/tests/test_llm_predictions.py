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
# 5. In-flight task is NOT cancelled when a new transcription fires
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_running_prediction_task_not_interrupted_on_new_transcription(sid):
    """A still-running prediction is left alone when new words arrive; no new task is spawned."""
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
        assert not first_task.done()  # still running (slow stream)

        # Second audio chunk — task is still running, should NOT be replaced
        await audio_pcm(sid, speech_pcm())
        second_task = sessions[sid].prediction_task

        await asyncio.sleep(0)

        # Same task object — not interrupted, not replaced
        assert second_task is first_task
        assert not first_task.cancelled()


# ---------------------------------------------------------------------------
# 6. Prompt uses "unstuck" framing, context as scope, 1-3 words, max_tokens=12
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_prompt_uses_unstuck_framing_and_context_scope(sid):
    """System prompt frames goal as getting speaker unstuck; context treated as scope."""
    captured_kwargs = {}

    @asynccontextmanager
    async def capturing_ctx(**kwargs):
        captured_kwargs.update(kwargs)
        mock_stream = MagicMock()
        mock_stream.text_stream = make_async_text_stream(["next"])
        yield mock_stream

    mock_client = MagicMock()
    mock_client.messages.stream = MagicMock(side_effect=lambda **kw: capturing_ctx(**kw))

    with (
        patch.object(routes_module, "_anthropic_client", mock_client),
        patch("routes.routes.sio") as mock_sio,
    ):
        mock_sio.emit = AsyncMock()
        await stream_llm_prediction(sid, "machine learning seminar", "the key insight is")

    system = captured_kwargs.get("system", "")
    user_msg = captured_kwargs.get("messages", [{}])[0].get("content", "")

    assert "unstuck" in system.lower() or "blank" in system.lower(), \
        "system prompt should reference getting the speaker unstuck"
    assert "1" in system and "3" in system, \
        "system prompt should specify 1 to 3 words"
    assert "scope" in system.lower() or "domain" in system.lower(), \
        "system prompt should reference context as scope/domain"
    assert "machine learning seminar" in user_msg, \
        "context should appear in user message"


@pytest.mark.asyncio
async def test_max_tokens_is_twelve(sid):
    """Claude is called with max_tokens=12 for short phrase predictions."""
    captured_kwargs = {}

    @asynccontextmanager
    async def capturing_ctx(**kwargs):
        captured_kwargs.update(kwargs)
        mock_stream = MagicMock()
        mock_stream.text_stream = make_async_text_stream(["go"])
        yield mock_stream

    mock_client = MagicMock()
    mock_client.messages.stream = MagicMock(side_effect=lambda **kw: capturing_ctx(**kw))

    with (
        patch.object(routes_module, "_anthropic_client", mock_client),
        patch("routes.routes.sio") as mock_sio,
    ):
        mock_sio.emit = AsyncMock()
        await stream_llm_prediction(sid, "context", "some transcript")

    assert captured_kwargs.get("max_tokens") == 12


# ---------------------------------------------------------------------------
# WS3: Latency profiling — timing fields in predictions payload
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_first_predictions_event_includes_prediction_ms(sid):
    """The first predictions event includes a prediction_ms timing field."""
    tokens = ["next", " step"]
    first_payload = {}

    async def capture(event, data, **_):
        if event == "predictions" and not first_payload:
            first_payload.update(data)

    mock_client = MagicMock()
    mock_client.messages.stream = MagicMock(return_value=make_stream_ctx(tokens))

    with (
        patch.object(routes_module, "_anthropic_client", mock_client),
        patch("routes.routes.sio") as mock_sio,
    ):
        mock_sio.emit = capture
        await stream_llm_prediction(sid, "context", "transcript here")

    assert "prediction_ms" in first_payload, (
        f"prediction_ms missing from first predictions payload: {first_payload}"
    )
    assert isinstance(first_payload["prediction_ms"], (int, float))
    assert first_payload["prediction_ms"] >= 0


@pytest.mark.asyncio
async def test_subsequent_predictions_events_omit_prediction_ms(sid):
    """Only the first predictions event carries prediction_ms — subsequent ones do not."""
    tokens = ["a", " b", " c"]
    all_payloads = []

    async def capture(event, data, **_):
        if event == "predictions":
            all_payloads.append(dict(data))

    mock_client = MagicMock()
    mock_client.messages.stream = MagicMock(return_value=make_stream_ctx(tokens))

    with (
        patch.object(routes_module, "_anthropic_client", mock_client),
        patch("routes.routes.sio") as mock_sio,
    ):
        mock_sio.emit = capture
        await stream_llm_prediction(sid, "context", "transcript")

    assert len(all_payloads) >= 2, "need at least 2 emit calls to test this"
    # First has prediction_ms
    assert "prediction_ms" in all_payloads[0]
    # Rest do not
    for payload in all_payloads[1:]:
        assert "prediction_ms" not in payload, (
            f"subsequent payload should not have prediction_ms: {payload}"
        )
