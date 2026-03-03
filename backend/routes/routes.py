import os
from collections import Counter, defaultdict
from typing import DefaultDict, Dict, List, Tuple

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
COMMON_STOPWORDS = {
    "the", "a", "an", "and", "or", "to", "of", "in", "on", "at", "for", "with",
    "we", "you", "i", "it", "is", "are", "was", "were", "be", "about", "if",
}

GENERIC_NEXT_WORDS = [
    "we",
    "can",
    "should",
    "need",
    "will",
    "then",
    "because",
    "this",
]

NEXT_WORD_PRIORS: Dict[str, List[str]] = {
    "if": ["we", "you", "it", "there", "this"],
    "we": ["can", "should", "need", "will", "are"],
    "about": ["the", "how", "why", "what", "ai"],
    "ai": ["models", "systems", "tools", "agents", "safety"],
    "and": ["then", "also", "we", "it", "that"],
    "because": ["it", "they", "we", "this", "that"],
}

TOPIC_HINTS: Dict[str, List[str]] = {
    "ai": ["models", "agents", "automation", "safety", "ethics", "impact"],
    "machine": ["learning", "data", "training", "inference", "model"],
    "startup": ["product", "market", "customers", "growth", "revenue"],
    "design": ["users", "interface", "experience", "system", "accessibility"],
}


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


def normalize_word(word: str) -> str:
    return word.strip(".,!?;:()[]{}\"'").lower()


def tokenize(text: str) -> List[str]:
    return [w for w in (normalize_word(part) for part in text.split()) if w]


def build_ngram_counts(words: List[str]) -> Tuple[
    DefaultDict[Tuple[str, str], Counter],
    DefaultDict[str, Counter],
    Counter,
]:
    tri_counts: DefaultDict[Tuple[str, str], Counter] = defaultdict(Counter)
    bi_counts: DefaultDict[str, Counter] = defaultdict(Counter)
    uni_counts: Counter = Counter()

    for i, word in enumerate(words):
        uni_counts[word] += 1
        if i >= 1:
            bi_counts[words[i - 1]][word] += 1
        if i >= 2:
            tri_counts[(words[i - 2], words[i - 1])][word] += 1

    return tri_counts, bi_counts, uni_counts


def build_weighted_transcript_counts(words: List[str]) -> Tuple[
    DefaultDict[Tuple[str, str], Counter],
    DefaultDict[str, Counter],
    Counter,
]:
    # Recency-weighted transcript statistics to make suggestions adapt quickly.
    tri_counts: DefaultDict[Tuple[str, str], Counter] = defaultdict(Counter)
    bi_counts: DefaultDict[str, Counter] = defaultdict(Counter)
    uni_counts: Counter = Counter()

    if not words:
        return tri_counts, bi_counts, uni_counts

    n = len(words)
    for i, word in enumerate(words):
        recency = 1.0 + (i / max(n - 1, 1))
        uni_counts[word] += recency
        if i >= 1:
            bi_counts[words[i - 1]][word] += recency
        if i >= 2:
            tri_counts[(words[i - 2], words[i - 1])][word] += recency

    return tri_counts, bi_counts, uni_counts


def build_context_topic_hints(context_words: List[str]) -> List[str]:
    hints: List[str] = []
    for word in context_words:
        hints.extend(TOPIC_HINTS.get(word, []))
    # Include key non-stopword context terms directly as candidates.
    hints.extend([w for w in context_words if w not in COMMON_STOPWORDS and len(w) > 3])
    deduped: List[str] = []
    for hint in hints:
        if hint not in deduped:
            deduped.append(hint)
    return deduped


def generate_predictions(context: str, transcript_text: str, count: int) -> List[str]:
    transcript_words = tokenize(transcript_text)
    context_words = tokenize(context)
    if not transcript_words and not context_words:
        return ["the", "and", "to", "of", "in"][:count]

    t_tri, t_bi, t_uni = build_weighted_transcript_counts(transcript_words)
    c_tri, c_bi, c_uni = build_ngram_counts(context_words)

    scores: Counter = Counter()

    # Current phrase seed: prioritize continuations based on the latest phrase.
    if len(transcript_words) >= 2:
        key2 = (transcript_words[-2], transcript_words[-1])
        for token, value in t_tri[key2].items():
            scores[token] += value * 3.0
        for token, value in c_tri[key2].items():
            scores[token] += value * 2.0

    if transcript_words:
        key1 = transcript_words[-1]
        for token, value in t_bi[key1].items():
            scores[token] += value * 2.4
        for token, value in c_bi[key1].items():
            scores[token] += value * 1.8
        for token in NEXT_WORD_PRIORS.get(key1, []):
            scores[token] += 1.2

    # Backoff priors from transcript and context.
    for token, value in t_uni.items():
        scores[token] += value * 0.35
    for token, value in c_uni.items():
        scores[token] += value * 0.2

    for token in build_context_topic_hints(context_words):
        scores[token] += 0.9

    stop_like = {"", "uh", "um"}
    recent_words = set(transcript_words[-4:])
    ranked_tokens = [
        token
        for token, _ in scores.most_common()
        if token not in stop_like and token not in recent_words and len(token) > 1
    ]
    if not ranked_tokens:
        ranked_tokens = [w for w in build_context_topic_hints(context_words) if w not in recent_words]
        ranked_tokens.extend(GENERIC_NEXT_WORDS)

    suggestions: List[str] = []
    for token in ranked_tokens:
        if token not in suggestions and token not in COMMON_STOPWORDS:
            suggestions.append(token)
        if len(suggestions) >= count:
            break

    if len(suggestions) < count:
        for fallback in GENERIC_NEXT_WORDS:
            if fallback not in suggestions:
                suggestions.append(fallback)
            if len(suggestions) >= count:
                break
    return suggestions


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
