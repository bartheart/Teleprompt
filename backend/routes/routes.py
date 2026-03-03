import os
from typing import Dict, List

import numpy as np
import socketio
import whisper
from fastapi import APIRouter

router = APIRouter()

sio = socketio.AsyncServer(
    async_mode="asgi",
    cors_allowed_origins="*",
    logger=False,
    engineio_logger=False,
)

WHISPER_MODEL_NAME = os.getenv("TELEPROMPT_WHISPER_MODEL", "base.en")
model = whisper.load_model(WHISPER_MODEL_NAME)
if model:
    print(f"Whisper model is loaded: {WHISPER_MODEL_NAME}")

SAMPLE_RATE = 16000
PROCESS_EVERY_SAMPLES = SAMPLE_RATE
TAIL_WINDOW_SAMPLES = SAMPLE_RATE * 6
MAX_TRANSCRIPT_HISTORY = 8
DEFAULT_PREDICTION_COUNT = 5


class SessionState:
    def __init__(self) -> None:
        self.context = ""
        self.audio_samples = np.array([], dtype=np.float32)
        self.last_processed_samples = 0
        self.is_processing = False
        self.full_transcript = ""
        self.prediction_count = DEFAULT_PREDICTION_COUNT


sessions: Dict[str, SessionState] = {}


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


def generate_predictions(context: str, transcript_text: str, count: int) -> List[str]:
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


@router.get("/")
async def home() -> str:
    return "Teleprompt backend is running"


@sio.event
async def connect(sid, environ):
    sessions[sid] = SessionState()
    await sio.emit("connect_response", {"status": "connected"}, room=sid)


@sio.event
async def disconnect(sid):
    sessions.pop(sid, None)


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
    if not state or state.is_processing:
        return

    pcm = np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0
    if pcm.size == 0:
        return

    state.audio_samples = np.concatenate((state.audio_samples, pcm))
    current_samples = len(state.audio_samples)
    if current_samples - state.last_processed_samples < PROCESS_EVERY_SAMPLES:
        return

    state.is_processing = True
    try:
        state.last_processed_samples = current_samples
        samples_for_asr = (
            state.audio_samples[-TAIL_WINDOW_SAMPLES:]
            if current_samples > TAIL_WINDOW_SAMPLES
            else state.audio_samples
        )
        transcription = model.transcribe(
            samples_for_asr,
            fp16=False,
            language="en",
            temperature=0.0,
            condition_on_previous_text=False,
        ).get("text", "").strip()

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
                },
                room=sid,
            )
            predictions = generate_predictions(
                context=state.context,
                transcript_text=state.full_transcript,
                count=state.prediction_count,
            )
            await sio.emit("predictions", {"items": predictions}, room=sid)

    except Exception as exc:  # pragma: no cover - runtime safety for live pipeline
        await sio.emit("server_error", {"message": str(exc)}, room=sid)
    finally:
        if len(state.audio_samples) > SAMPLE_RATE * 20:
            state.audio_samples = state.audio_samples[-SAMPLE_RATE * 20 :]
            state.last_processed_samples = len(state.audio_samples)
        state.is_processing = False
