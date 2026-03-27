import asyncio
import logging
import os
import time
from typing import Dict, List, Optional

import numpy as np
import socketio
from anthropic import AsyncAnthropic
from faster_whisper import WhisperModel
from fastapi import APIRouter

router = APIRouter()
logger = logging.getLogger("teleprompt.latency")

sio = socketio.AsyncServer(
    async_mode="asgi",
    cors_allowed_origins="*",
    logger=False,
    engineio_logger=False,
)

WHISPER_MODEL_NAME = os.getenv("TELEPROMPT_WHISPER_MODEL", "tiny.en")
model = None
model_load_lock = asyncio.Lock()

SAMPLE_RATE = 16000
PROCESS_EVERY_SAMPLES = 8000
TAIL_WINDOW_SAMPLES = SAMPLE_RATE * 3
MAX_BUFFER_SAMPLES = SAMPLE_RATE * 20
MAX_TRANSCRIPT_HISTORY = 8
DEFAULT_PREDICTION_COUNT = 5
SILENCE_RMS_THRESHOLD = 0.01  # float32 normalized; ~-40 dBFS

_ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
_anthropic_client: Optional[AsyncAnthropic] = (
    AsyncAnthropic(api_key=_ANTHROPIC_API_KEY) if _ANTHROPIC_API_KEY else None
)


class SessionState:
    def __init__(self) -> None:
        self.context = ""
        # Double-buffer: audio always accumulates here, never dropped
        self.active_buffer = np.array([], dtype=np.float32)
        self.last_processed_samples = 0
        # Lock instead of bool flag — audio_pcm still returns early if inference
        # is running, but only AFTER accumulating the new chunk above
        self.inference_lock = asyncio.Lock()
        self.full_transcript = ""
        self.prediction_count = DEFAULT_PREDICTION_COUNT
        self.last_audio_received_ms: Optional[int] = None
        self.last_client_sent_at_ms: Optional[int] = None
        self.last_batch_id: Optional[int] = None
        self.prediction_task: Optional[asyncio.Task] = None


sessions: Dict[str, SessionState] = {}


async def get_model():
    global model
    if model is not None:
        return model

    async with model_load_lock:
        if model is not None:
            return model
        model = await asyncio.to_thread(WhisperModel, WHISPER_MODEL_NAME, device="cpu", compute_type="int8")
        print(f"Whisper model is loaded: {WHISPER_MODEL_NAME}")
        return model


def append_delta(existing_text: str, new_text: str) -> str:
    existing_words = existing_text.split()
    new_words = new_text.split()
    if not new_words:
        return ""

    max_overlap = min(len(existing_words), len(new_words))
    overlap = 0
    for size in range(max_overlap, 0, -1):
        if existing_words[-size:] == new_words[:size]:
            overlap = size
            break

    return " ".join(new_words[overlap:]).strip()


def is_silent(samples: np.ndarray, threshold: float = SILENCE_RMS_THRESHOLD) -> bool:
    if samples.size == 0:
        return True
    return float(np.sqrt(np.mean(samples ** 2))) < threshold


def _bigram_fallback(context: str, transcript_text: str, count: int) -> List[str]:
    text = transcript_text.strip().lower()
    words = [w.strip(".,!?;:()[]{}\"'") for w in text.split() if w.strip(".,!?;:()[]{}\"'")]
    if not words:
        context_words = [w.strip(".,!?;:()[]{}\"'").lower() for w in context.split() if len(w) > 3]
        return context_words[:count] or ["the", "and", "to", "of", "in"][:count]

    last_word = words[-1]
    followups: Dict[str, Dict[str, int]] = {}
    for i in range(len(words) - 1):
        current_word = words[i]
        next_word = words[i + 1]
        followups.setdefault(current_word, {})
        followups[current_word][next_word] = followups[current_word].get(next_word, 0) + 1

    ranked = sorted(followups.get(last_word, {}).items(), key=lambda x: x[1], reverse=True)
    dynamic = [word for word, _ in ranked]

    context_words = [w.strip(".,!?;:()[]{}\"'").lower() for w in context.split() if len(w) > 3]
    candidates: List[str] = []
    candidates.extend(dynamic)
    candidates.extend(words[-4:])
    candidates.extend(context_words[:8])
    candidates.extend(["and", "so", "because", "then", "the"])

    result: List[str] = []
    for item in candidates:
        if item and item not in result:
            result.append(item)
        if len(result) >= count:
            break
    return result


async def stream_llm_prediction(sid: str, context: str, transcript_text: str) -> None:
    """
    Fire-and-forget coroutine. Streams a 4-8 word phrase from Claude Haiku,
    emitting progressive `predictions` updates as tokens arrive.
    Falls back to bigram predictions silently on any failure or missing key.
    """
    if _anthropic_client is None:
        fallback = _bigram_fallback(context, transcript_text, 1)
        await sio.emit("predictions", {"items": fallback}, room=sid)
        return

    system_prompt = (
        "You are a real-time speech assistant helping a speaker recover their train of "
        "thought mid-sentence. Given the speaker's preparation notes (context) and what "
        "they have said so far (transcript), complete their next thought with a natural, "
        "fluent phrase of exactly 4 to 8 words. Output ONLY the phrase — no punctuation, "
        "no explanation, no quotation marks."
    )
    user_message = (
        f"Context (speaker's notes):\n{context or '(none)'}\n\n"
        f"Transcript so far:\n{transcript_text or '(none)'}\n\n"
        "Continue the speaker's next phrase (4-8 words):"
    )

    accumulated = ""
    try:
        async with _anthropic_client.messages.stream(
            model="claude-haiku-4-5",
            max_tokens=24,
            temperature=0.4,
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}],
        ) as stream:
            async for text_delta in stream.text_stream:
                accumulated = (accumulated + text_delta).strip()
                if accumulated:
                    await sio.emit("predictions", {"items": [accumulated]}, room=sid)

        if not accumulated:
            fallback = _bigram_fallback(context, transcript_text, 1)
            if fallback:
                await sio.emit("predictions", {"items": fallback}, room=sid)

    except asyncio.CancelledError:
        raise  # let cancellation propagate cleanly
    except Exception:
        fallback = _bigram_fallback(context, transcript_text, 1)
        if fallback:
            await sio.emit("predictions", {"items": fallback}, room=sid)


@router.get("/")
async def home() -> str:
    return "Teleprompt backend is running"


@sio.event
async def connect(sid, environ):
    sessions[sid] = SessionState()
    await sio.emit("connect_response", {"status": "connected"}, room=sid)


@sio.event
async def disconnect(sid):
    state = sessions.pop(sid, None)
    if state and state.prediction_task and not state.prediction_task.done():
        state.prediction_task.cancel()


@sio.event
async def start_session(sid, payload: Dict[str, str]):
    state = sessions.get(sid)
    if not state:
        return

    state.context = (payload or {}).get("context", "").strip()
    state.full_transcript = ""
    prediction_count = (payload or {}).get("predictionCount", DEFAULT_PREDICTION_COUNT)
    try:
        state.prediction_count = max(1, min(int(prediction_count), 10))
    except (TypeError, ValueError):
        state.prediction_count = DEFAULT_PREDICTION_COUNT


@sio.event
async def audio_pcm(sid, data: bytes):
    state = sessions.get(sid)
    if not state:
        return
    receive_ms = int(time.time() * 1000)
    total_start = time.perf_counter()

    client_sent_at_ms: Optional[int] = None
    batch_id: Optional[int] = None
    pcm_payload = data
    if isinstance(data, dict):
        client_sent_at_ms = data.get("client_sent_at_ms")
        batch_id = data.get("batch_id")
        pcm_payload = data.get("pcm")
    if pcm_payload is None:
        return

    pcm = np.frombuffer(pcm_payload, dtype=np.int16).astype(np.float32) / 32768.0
    if pcm.size == 0:
        return

    state.last_audio_received_ms = receive_ms
    if client_sent_at_ms is not None:
        state.last_client_sent_at_ms = client_sent_at_ms
    if batch_id is not None:
        state.last_batch_id = batch_id

    # Double-buffer: always accumulate before any gate — audio is never dropped
    state.active_buffer = np.concatenate((state.active_buffer, pcm))

    # Trim oldest audio to bound memory; adjust cursor so trigger math stays valid
    if len(state.active_buffer) > MAX_BUFFER_SAMPLES:
        excess = len(state.active_buffer) - MAX_BUFFER_SAMPLES
        state.active_buffer = state.active_buffer[excess:]
        state.last_processed_samples = max(0, state.last_processed_samples - excess)

    current_samples = len(state.active_buffer)

    # Not enough new audio yet to warrant another inference pass
    if current_samples - state.last_processed_samples < PROCESS_EVERY_SAMPLES:
        return

    # Inference already running — audio is safely in active_buffer, skip triggering
    if state.inference_lock.locked():
        return

    async with state.inference_lock:
        # Snapshot cursor at the moment inference fires; active_buffer grows freely during inference
        state.last_processed_samples = len(state.active_buffer)
        samples_for_asr = (
            state.active_buffer[-TAIL_WINDOW_SAMPLES:]
            if len(state.active_buffer) > TAIL_WINDOW_SAMPLES
            else state.active_buffer.copy()
        )

        if is_silent(samples_for_asr):
            return

        transcribe_ms = 0.0
        try:
            loaded_model = await get_model()
            transcribe_start = time.perf_counter()
            segments, _ = loaded_model.transcribe(
                samples_for_asr,
                language="en",
                temperature=0.0,
                condition_on_previous_text=False,
            )
            transcription = " ".join(segment.text for segment in segments).strip()
            transcribe_ms = (time.perf_counter() - transcribe_start) * 1000.0

            if transcription:
                delta = append_delta(state.full_transcript, transcription)
                if delta:
                    state.full_transcript = f"{state.full_transcript} {delta}".strip()

                current_word = state.full_transcript.split()[-1] if state.full_transcript else ""
                await sio.emit(
                    "transcription",
                    {
                        "text": current_word,
                        "current_word": current_word,
                        "delta_text": delta,
                        "full_text": state.full_transcript,
                        "batch_id": state.last_batch_id,
                        "transcribe_ms": round(transcribe_ms),
                    },
                    room=sid,
                )

                # Cancel stale prediction and stream a new one non-blocking
                if state.prediction_task and not state.prediction_task.done():
                    state.prediction_task.cancel()
                state.prediction_task = asyncio.create_task(
                    stream_llm_prediction(sid, state.context, state.full_transcript)
                )

            total_ms = (time.perf_counter() - total_start) * 1000.0
            buffered_seconds = len(state.active_buffer) / SAMPLE_RATE
            client_to_server_ms = None
            if state.last_client_sent_at_ms is not None:
                client_to_server_ms = receive_ms - state.last_client_sent_at_ms
            if logger.isEnabledFor(logging.INFO):
                logger.info(
                    "audio_pcm_processed sid=%s transcribe_ms=%.1f total_ms=%.1f buffered_s=%.2f client_to_server_ms=%s",
                    sid,
                    transcribe_ms,
                    total_ms,
                    buffered_seconds,
                    f"{client_to_server_ms:.1f}" if client_to_server_ms is not None else "n/a",
                )

        except Exception as exc:  # pragma: no cover - runtime safety for live pipeline
            await sio.emit("server_error", {"message": str(exc)}, room=sid)
