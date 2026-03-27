"""
Tests for the audio_pcm handler: buffering, inference gating,
buffer trimming, and error recovery.
"""

import math
import sys
import types
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest

if "faster_whisper" not in sys.modules:
    fw = types.ModuleType("faster_whisper")
    fw.WhisperModel = MagicMock  # type: ignore[attr-defined]
    sys.modules["faster_whisper"] = fw

from routes.routes import (
    MAX_BUFFER_SAMPLES,
    PROCESS_EVERY_SAMPLES,
    SAMPLE_RATE,
    SessionState,
    audio_pcm,
    sessions,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_pcm(samples: np.ndarray) -> bytes:
    return (samples * 32767).astype(np.int16).tobytes()


def speech(n: int = 9000, freq: float = 440.0) -> np.ndarray:
    t = np.linspace(0, n / SAMPLE_RATE, n, endpoint=False)
    return (np.sin(2 * math.pi * freq * t) * 0.5).astype(np.float32)


def silence(n: int = 9000) -> np.ndarray:
    return np.zeros(n, dtype=np.float32)


@pytest.fixture
def sid():
    _sid = "pipeline-test-001"
    sessions[_sid] = SessionState()
    yield _sid
    sessions.pop(_sid, None)


def mock_model_with(text: str = "hello world"):
    seg = MagicMock()
    seg.text = text
    m = MagicMock()
    m.transcribe = MagicMock(return_value=([seg], MagicMock()))
    return m


# ---------------------------------------------------------------------------
# Buffer accumulation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_audio_accumulates_in_buffer(sid):
    """Audio bytes are stored in active_buffer regardless of inference gating."""
    pcm = make_pcm(speech(4000))  # below PROCESS_EVERY_SAMPLES — no inference
    with patch("routes.routes.sio") as mock_sio:
        mock_sio.emit = AsyncMock()
        await audio_pcm(sid, pcm)
    assert sessions[sid].active_buffer.size > 0


@pytest.mark.asyncio
async def test_buffer_does_not_exceed_max(sid):
    """Buffer is trimmed to MAX_BUFFER_SAMPLES when overfull."""
    big_chunk = make_pcm(speech(MAX_BUFFER_SAMPLES + 10000))
    with (
        patch("routes.routes.get_model", new=AsyncMock(return_value=mock_model_with())),
        patch("routes.routes.sio") as mock_sio,
    ):
        mock_sio.emit = AsyncMock()
        await audio_pcm(sid, big_chunk)
    assert sessions[sid].active_buffer.size <= MAX_BUFFER_SAMPLES


@pytest.mark.asyncio
async def test_unknown_sid_does_not_raise():
    """Handler is safe for unregistered session IDs."""
    pcm = make_pcm(speech(9000))
    await audio_pcm("nonexistent-sid-abc", pcm)  # should not raise


@pytest.mark.asyncio
async def test_empty_payload_does_not_raise(sid):
    """Zero-length PCM is handled gracefully."""
    await audio_pcm(sid, b"")


# ---------------------------------------------------------------------------
# Inference gating
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_inference_not_triggered_below_threshold(sid):
    """Whisper is not called when fewer than PROCESS_EVERY_SAMPLES accumulate."""
    model = mock_model_with()
    pcm = make_pcm(speech(PROCESS_EVERY_SAMPLES - 100))
    with (
        patch("routes.routes.get_model", new=AsyncMock(return_value=model)),
        patch("routes.routes.sio") as mock_sio,
    ):
        mock_sio.emit = AsyncMock()
        await audio_pcm(sid, pcm)
    model.transcribe.assert_not_called()


@pytest.mark.asyncio
async def test_inference_triggered_at_threshold(sid):
    """Whisper is called once enough speech samples accumulate."""
    model = mock_model_with("hello")
    pcm = make_pcm(speech(PROCESS_EVERY_SAMPLES + 100))
    with (
        patch("routes.routes.get_model", new=AsyncMock(return_value=model)),
        patch("routes.routes.sio") as mock_sio,
    ):
        mock_sio.emit = AsyncMock()
        await audio_pcm(sid, pcm)
    model.transcribe.assert_called_once()


# ---------------------------------------------------------------------------
# Transcription output
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_full_transcript_grows_over_calls(sid):
    """Successive speech calls append to the full transcript."""
    model = MagicMock()
    call_count = 0

    def fake_transcribe(samples, **_):
        nonlocal call_count
        call_count += 1
        seg = MagicMock()
        seg.text = "word" if call_count == 1 else "word next"
        return ([seg], MagicMock())

    model.transcribe = fake_transcribe

    with (
        patch("routes.routes.get_model", new=AsyncMock(return_value=model)),
        patch("routes.routes.sio") as mock_sio,
    ):
        mock_sio.emit = AsyncMock()
        await audio_pcm(sid, make_pcm(speech(9000)))
        await audio_pcm(sid, make_pcm(speech(9000)))

    assert "next" in sessions[sid].full_transcript


@pytest.mark.asyncio
async def test_transcription_event_payload_has_expected_keys(sid):
    """The transcription Socket.IO event includes full_text and current_word."""
    model = mock_model_with("hello world")
    emitted = []

    async def capture_emit(event, data, **_):
        emitted.append((event, data))

    with (
        patch("routes.routes.get_model", new=AsyncMock(return_value=model)),
        patch("routes.routes.sio") as mock_sio,
    ):
        mock_sio.emit = capture_emit
        await audio_pcm(sid, make_pcm(speech(9000)))

    transcription_events = [d for e, d in emitted if e == "transcription"]
    assert transcription_events, "no transcription event emitted"
    payload = transcription_events[0]
    assert "full_text" in payload
    assert "current_word" in payload


@pytest.mark.asyncio
async def test_predictions_event_emitted_after_transcription(sid):
    """A predictions event follows every transcription event."""
    model = mock_model_with("one two three")
    emitted_events = []

    async def capture_emit(event, data, **_):
        emitted_events.append(event)

    with (
        patch("routes.routes.get_model", new=AsyncMock(return_value=model)),
        patch("routes.routes.sio") as mock_sio,
    ):
        mock_sio.emit = capture_emit
        await audio_pcm(sid, make_pcm(speech(9000)))

    assert "predictions" in emitted_events


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_whisper_exception_emits_server_error(sid):
    """If Whisper raises, a server_error event is emitted instead of crashing."""
    model = MagicMock()
    model.transcribe = MagicMock(side_effect=RuntimeError("model crashed"))
    emitted_events = []

    async def capture_emit(event, data, **_):
        emitted_events.append(event)

    with (
        patch("routes.routes.get_model", new=AsyncMock(return_value=model)),
        patch("routes.routes.sio") as mock_sio,
    ):
        mock_sio.emit = capture_emit
        await audio_pcm(sid, make_pcm(speech(9000)))

    assert "server_error" in emitted_events


# ---------------------------------------------------------------------------
# Dict payload (client sends metadata alongside PCM)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_dict_payload_with_metadata(sid):
    """Handler accepts dict payload with pcm + client_sent_at_ms + batch_id."""
    model = mock_model_with("test")
    pcm_bytes = make_pcm(speech(9000))
    payload = {
        "pcm": pcm_bytes,
        "client_sent_at_ms": 1700000000000,
        "batch_id": 42,
    }
    with (
        patch("routes.routes.get_model", new=AsyncMock(return_value=model)),
        patch("routes.routes.sio") as mock_sio,
    ):
        mock_sio.emit = AsyncMock()
        await audio_pcm(sid, payload)
    assert sessions[sid].last_batch_id == 42


@pytest.mark.asyncio
async def test_dict_payload_missing_pcm_does_not_raise(sid):
    """Dict payload without 'pcm' key is handled gracefully."""
    await audio_pcm(sid, {"client_sent_at_ms": 123})
