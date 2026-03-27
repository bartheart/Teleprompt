"""
Tests for silence-gated transcription (feature/silence-detection).

Covers:
  - is_silent() unit tests (edge cases + threshold boundary)
  - audio_pcm handler integration: Whisper is skipped on silence, called on speech
"""

import asyncio
import math
import sys
import types
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest

# ---------------------------------------------------------------------------
# Make faster_whisper importable without the real package installed in tests
# ---------------------------------------------------------------------------
if "faster_whisper" not in sys.modules:
    fw = types.ModuleType("faster_whisper")
    fw.WhisperModel = MagicMock  # type: ignore[attr-defined]
    sys.modules["faster_whisper"] = fw

from routes.routes import (  # noqa: E402
    SILENCE_RMS_THRESHOLD,
    SessionState,
    audio_pcm,
    is_silent,
    sessions,
)


# ===========================================================================
# Helpers
# ===========================================================================

def make_pcm_bytes(samples: np.ndarray) -> bytes:
    """Convert float32 samples [-1, 1] to raw int16 PCM bytes."""
    int16 = (samples * 32767).astype(np.int16)
    return int16.tobytes()


def sine_wave(frequency: float = 440.0, duration_s: float = 0.5, sample_rate: int = 16000) -> np.ndarray:
    """Return float32 sine samples at the given frequency (clearly above threshold)."""
    t = np.linspace(0, duration_s, int(sample_rate * duration_s), endpoint=False)
    return (np.sin(2 * math.pi * frequency * t) * 0.5).astype(np.float32)


def silent_samples(n: int = 8000) -> np.ndarray:
    """Return n float32 zero samples."""
    return np.zeros(n, dtype=np.float32)


def near_silent_samples(n: int = 8000, amplitude: float = 0.005) -> np.ndarray:
    """Return low-amplitude noise clearly below SILENCE_RMS_THRESHOLD."""
    rng = np.random.default_rng(42)
    return (rng.uniform(-amplitude, amplitude, n)).astype(np.float32)


# ===========================================================================
# Unit tests: is_silent()
# ===========================================================================

class TestIsSilent:
    def test_empty_array_is_silent(self):
        assert is_silent(np.array([], dtype=np.float32)) is True

    def test_all_zeros_is_silent(self):
        assert is_silent(silent_samples(16000)) is True

    def test_near_silence_below_threshold(self):
        samples = near_silent_samples(amplitude=SILENCE_RMS_THRESHOLD * 0.5)
        assert is_silent(samples) is True

    def test_speech_amplitude_not_silent(self):
        assert is_silent(sine_wave()) is False

    def test_exactly_at_threshold_is_silent(self):
        # Constant signal whose RMS == threshold → treated as silent (strict <)
        samples = np.full(8000, SILENCE_RMS_THRESHOLD, dtype=np.float32)
        assert is_silent(samples) is True

    def test_just_above_threshold_not_silent(self):
        amplitude = SILENCE_RMS_THRESHOLD * 1.5
        samples = np.full(8000, amplitude, dtype=np.float32)
        assert is_silent(samples) is False

    def test_custom_threshold(self):
        samples = sine_wave()  # RMS ~ 0.35
        assert is_silent(samples, threshold=0.5) is True
        assert is_silent(samples, threshold=0.1) is False


# ===========================================================================
# Integration tests: audio_pcm handler skips Whisper on silence
# ===========================================================================

@pytest.fixture
def session_id():
    sid = "test-sid-001"
    sessions[sid] = SessionState()
    yield sid
    sessions.pop(sid, None)


@pytest.mark.asyncio
async def test_silent_audio_skips_whisper(session_id):
    """Whisper transcribe must NOT be called when the tail window is silent."""
    mock_model = MagicMock()
    mock_model.transcribe = MagicMock(return_value=([], MagicMock()))

    with (
        patch("routes.routes.get_model", new=AsyncMock(return_value=mock_model)),
        patch("routes.routes.sio") as mock_sio,
    ):
        mock_sio.emit = AsyncMock()

        # Send enough silent PCM to trigger the inference gate (>= PROCESS_EVERY_SAMPLES)
        pcm = make_pcm_bytes(silent_samples(9000))
        await audio_pcm(session_id, pcm)

        mock_model.transcribe.assert_not_called()


@pytest.mark.asyncio
async def test_speech_audio_calls_whisper(session_id):
    """Whisper transcribe MUST be called when the tail window contains speech."""
    fake_segment = MagicMock()
    fake_segment.text = "hello world"
    mock_model = MagicMock()
    mock_model.transcribe = MagicMock(return_value=([fake_segment], MagicMock()))

    with (
        patch("routes.routes.get_model", new=AsyncMock(return_value=mock_model)),
        patch("routes.routes.sio") as mock_sio,
    ):
        mock_sio.emit = AsyncMock()

        pcm = make_pcm_bytes(sine_wave(duration_s=0.6))  # 9600 samples
        await audio_pcm(session_id, pcm)

        mock_model.transcribe.assert_called_once()


@pytest.mark.asyncio
async def test_speech_emits_transcription_event(session_id):
    """A transcription Socket.IO event is emitted when speech is detected."""
    fake_segment = MagicMock()
    fake_segment.text = "testing one two"
    mock_model = MagicMock()
    mock_model.transcribe = MagicMock(return_value=([fake_segment], MagicMock()))

    with (
        patch("routes.routes.get_model", new=AsyncMock(return_value=mock_model)),
        patch("routes.routes.sio") as mock_sio,
    ):
        mock_sio.emit = AsyncMock()

        pcm = make_pcm_bytes(sine_wave(duration_s=0.6))
        await audio_pcm(session_id, pcm)

        emitted_events = [call.args[0] for call in mock_sio.emit.call_args_list]
        assert "transcription" in emitted_events


@pytest.mark.asyncio
async def test_silent_audio_emits_no_events(session_id):
    """No Socket.IO events are emitted during silence."""
    mock_model = MagicMock()

    with (
        patch("routes.routes.get_model", new=AsyncMock(return_value=mock_model)),
        patch("routes.routes.sio") as mock_sio,
    ):
        mock_sio.emit = AsyncMock()

        pcm = make_pcm_bytes(silent_samples(9000))
        await audio_pcm(session_id, pcm)

        mock_sio.emit.assert_not_called()
