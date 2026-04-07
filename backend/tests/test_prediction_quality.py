"""
Quality gate tests for stream_llm_prediction.

Covers:
  1. Claude output emitted as a complete phrase
  2. Output trimmed to max 3 words if Claude over-generates
  3. Prediction skipped/replaced when it repeats the last spoken word
  4. Bigram fallback on API error returns non-empty result
  5. Stream completes within 2 seconds on a fast mock
"""

import asyncio
import sys
import time
import types
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

if "faster_whisper" not in sys.modules:
    fw = types.ModuleType("faster_whisper")
    fw.WhisperModel = MagicMock()
    sys.modules["faster_whisper"] = fw

import routes.routes as routes_module
from routes.routes import SessionState, sessions, stream_llm_prediction


def make_async_text_stream(tokens: list[str]):
    async def _gen():
        for t in tokens:
            yield t
    return _gen()


def make_stream_ctx(tokens: list[str]):
    @asynccontextmanager
    async def _ctx():
        mock_stream = MagicMock()
        mock_stream.text_stream = make_async_text_stream(tokens)
        yield mock_stream
    return _ctx()


@pytest.fixture
def sid():
    _sid = "quality-test-sid-001"
    sessions[_sid] = SessionState()
    yield _sid
    sessions.pop(_sid, None)


# ---------------------------------------------------------------------------
# 1. Output emitted as a complete phrase (not truncated prematurely)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_prediction_emits_complete_phrase(sid):
    """Final emitted prediction is the full accumulated phrase (up to 3 words)."""
    tokens = ["deep", " focus"]
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
        await stream_llm_prediction(sid, "productivity podcast", "the key to staying")

    assert emitted[-1] == "deep focus"


# ---------------------------------------------------------------------------
# 2. Output trimmed to max 3 words
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_prediction_trimmed_to_three_words(sid):
    """If Claude streams more than 3 words, output is capped at 3."""
    tokens = ["this", " is", " way", " too", " long", " phrase"]
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
        await stream_llm_prediction(sid, "context", "the speaker said")

    assert len(emitted[-1].split()) == 3


# ---------------------------------------------------------------------------
# 3. No-repeat guard: prediction replaced when it repeats the last spoken word
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_no_repeat_guard_replaces_with_fallback(sid):
    """Prediction starting with the last spoken word is replaced by bigram fallback."""
    # Transcript ends with "said"; Claude returns "said something else" → should be replaced
    tokens = ["said", " something", " else"]

    emitted_items = []

    async def capture(event, data, **_):
        if event == "predictions":
            emitted_items.append(data["items"][0])

    mock_client = MagicMock()
    mock_client.messages.stream = MagicMock(return_value=make_stream_ctx(tokens))

    with (
        patch.object(routes_module, "_anthropic_client", mock_client),
        patch("routes.routes.sio") as mock_sio,
    ):
        mock_sio.emit = capture
        await stream_llm_prediction(sid, "context", "the speaker said")

    # Final prediction must NOT start with "said"
    assert emitted_items, "no prediction emitted"
    assert not emitted_items[-1].lower().startswith("said"), (
        f"prediction repeated last word: {emitted_items[-1]!r}"
    )


# ---------------------------------------------------------------------------
# 4. Fallback on API error returns non-empty result
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fallback_on_api_error_returns_non_empty(sid):
    """Bigram fallback fires on Claude error and returns at least one word."""
    @asynccontextmanager
    async def error_ctx():
        raise RuntimeError("api timeout")
        yield  # noqa: unreachable

    mock_client = MagicMock()
    mock_client.messages.stream = MagicMock(return_value=error_ctx())

    emitted = []

    async def capture(event, data, **_):
        if event == "predictions":
            emitted.append(data["items"])

    with (
        patch.object(routes_module, "_anthropic_client", mock_client),
        patch("routes.routes.sio") as mock_sio,
    ):
        mock_sio.emit = capture
        await stream_llm_prediction(sid, "productivity", "the key thing is")

    assert len(emitted) == 1
    assert len(emitted[0]) > 0
    assert all(isinstance(w, str) and w.strip() for w in emitted[0])


# ---------------------------------------------------------------------------
# 5. Latency budget: stream completes within 2 seconds on a fast mock
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_stream_completes_within_2_seconds(sid):
    """stream_llm_prediction completes in under 2s on a fast mock stream."""
    tokens = ["next", " step"]
    mock_client = MagicMock()
    mock_client.messages.stream = MagicMock(return_value=make_stream_ctx(tokens))

    with (
        patch.object(routes_module, "_anthropic_client", mock_client),
        patch("routes.routes.sio") as mock_sio,
    ):
        mock_sio.emit = AsyncMock()
        start = time.perf_counter()
        await stream_llm_prediction(sid, "context", "transcript here")
        elapsed = time.perf_counter() - start

    assert elapsed < 2.0, f"stream took {elapsed:.2f}s — exceeded 2s budget"
