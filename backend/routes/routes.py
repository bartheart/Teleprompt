from io import BytesIO
from typing import Dict, List

import numpy as np
import socketio
import whisper
from fastapi import APIRouter
from pydub import AudioSegment

router = APIRouter()

sio = socketio.AsyncServer(
    async_mode="asgi",
    cors_allowed_origins="*",
    logger=True,
    engineio_logger=True,
)

model = whisper.load_model("turbo")
if model:
    print("Whisper model is loaded")

MIME_TO_EXTENSION = {
    "audio/webm": "webm",
    "audio/webm;codecs=opus": "webm",
    "audio/mp4": "mp4",
    "audio/mp4;codecs=opus": "mp4",
    "audio/ogg": "ogg",
    "audio/ogg;codecs=opus": "ogg",
}

SAMPLE_RATE = 16000
BUFFER_MIN_BYTES = SAMPLE_RATE
MAX_TRANSCRIPT_HISTORY = 8
DEFAULT_PREDICTION_COUNT = 5


class SessionState:
    def __init__(self) -> None:
        self.context = ""
        self.mime_extension = "webm"
        self.audio_buffer = BytesIO()
        self.is_processing = False
        self.transcript_history: List[str] = []
        self.prediction_count = DEFAULT_PREDICTION_COUNT


sessions: Dict[str, SessionState] = {}


def generate_predictions(context: str, transcript_history: List[str], count: int) -> List[str]:
    joined_text = " ".join(transcript_history).strip()
    context_words = [word.strip(".,!?").lower() for word in context.split() if len(word) > 4]
    recent_words = [word.strip(".,!?").lower() for word in joined_text.split()[-12:]]

    candidates: List[str] = []
    candidates.extend(["so", "and", "because", "for example", "the key point is"])
    candidates.extend(recent_words[-4:])
    candidates.extend(context_words[:6])

    deduped: List[str] = []
    for item in candidates:
        if item and item not in deduped:
            deduped.append(item)
        if len(deduped) >= count:
            break
    return deduped


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
    prediction_count = (payload or {}).get("predictionCount", DEFAULT_PREDICTION_COUNT)
    try:
        state.prediction_count = max(1, min(int(prediction_count), 10))
    except (TypeError, ValueError):
        state.prediction_count = DEFAULT_PREDICTION_COUNT


@sio.event
async def mime_type(sid, media_type: str):
    state = sessions.get(sid)
    if not state:
        return
    state.mime_extension = MIME_TO_EXTENSION.get(media_type, "webm")


@sio.event
async def audio_data(sid, data: bytes):
    state = sessions.get(sid)
    if not state or state.is_processing:
        return

    state.audio_buffer.write(data)
    if state.audio_buffer.tell() < BUFFER_MIN_BYTES:
        return

    state.is_processing = True
    try:
        state.audio_buffer.seek(0)
        audio_segment = AudioSegment.from_file(
            state.audio_buffer,
            codec="opus",
            format=state.mime_extension,
            parameters=["-ar", str(SAMPLE_RATE)],
        )

        samples = np.array(audio_segment.get_array_of_samples(), dtype=np.float32) / 32768.0
        transcription = model.transcribe(samples).get("text", "").strip()

        if transcription:
            state.transcript_history.append(transcription)
            if len(state.transcript_history) > MAX_TRANSCRIPT_HISTORY:
                state.transcript_history = state.transcript_history[-MAX_TRANSCRIPT_HISTORY:]

            await sio.emit("transcription", {"text": transcription}, room=sid)
            predictions = generate_predictions(
                context=state.context,
                transcript_history=state.transcript_history,
                count=state.prediction_count,
            )
            await sio.emit("predictions", {"items": predictions}, room=sid)

    except Exception as exc:  # pragma: no cover - runtime safety for live pipeline
        await sio.emit("server_error", {"message": str(exc)}, room=sid)
    finally:
        state.audio_buffer = BytesIO()
        state.is_processing = False
