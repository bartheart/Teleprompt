# Prediction System Redesign

**Date:** 2026-04-06
**Status:** Approved
**Target audience:** Podcasters and content creators who need a zero-retake speech recovery tool

---

## Problem

The current prediction system has three concrete failures:

1. **Latency is visible.** Claude fires after every Whisper transcription and the user watches it compute. The "thinking" is on screen.
2. **One word appears instead of a phrase.** The streaming animation re-mounts the element on every token (`key={prediction}`), making 3-word phrases appear as single flashing words. Fixed in prompter but the underlying display model is still wrong.
3. **Predictions are not accurate enough.** The prompt doesn't balance grammatical continuation with domain relevance, and too much transcript context dilutes Claude's focus.

---

## Goal

A speaker blanks mid-sentence. Within 1.2 seconds of silence, a 1–3 word phrase appears — large, clear, instantly readable — that is both a natural continuation of what they just said AND relevant to their topic. They read it, resume, the phrase fades. No retake. No cut.

---

## Spec Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Prediction trigger | Hybrid — dim during speech, prominent on pause | Targets blank recovery without distracting during flow |
| Pause threshold | 1.2s of sub-threshold amplitude | Catches genuine blanks, ignores breath pauses (~0.3–0.6s) |
| Amplitude threshold | 0.05 (normalised RMS) | Tunable; separates speech from silence reliably |
| Prominent animation | `fadeSlideUp 180ms` to full size | Already in CSS; familiar, not jarring |
| Resume behaviour | 0.5s fade-out when amplitude rises | Smooth exit, speaker stays focused |
| Prediction length | 1–3 words, Claude decides dynamically | 1 if unambiguous, up to 3 for specificity |
| Prediction quality | Grammatically natural AND domain-relevant | Both required; neither alone is sufficient |
| Transcript context window | Last 30 words | Enough grammar context, focused enough for relevance |
| Temperature | 0.2 | Reliable continuations over creative variance |
| Max tokens | 12 | 3 words ≈ 4–6 tokens; headroom without waste |
| Pause detection location | Frontend (amplitude data already available) | No new Socket.IO events; keeps display logic in UI |

---

## Architecture

### During Speech

```
Audio → Whisper → new words → Claude computes prediction
                                     ↓
                              Prediction rendered small + dim (opacity 0.25, font 0.9rem)
                              No animation, no distraction
```

### On Pause (1.2s silence)

```
Amplitude < 0.05 for 1.2s
        ↓
isPaused = true
        ↓
Prediction animates to full size (clamp(3rem, 8vw, 5rem), opacity 1.0, fadeSlideUp)
Already computed — zero additional latency
```

### On Resume

```
Amplitude > 0.05
        ↓
isPaused = false
        ↓
Prediction fades out (opacity 0 over 500ms)
Next Claude result will be ready before next blank
```

---

## Workstreams

### WS1 — Pause-triggered display (`feature/pause-triggered-display`)

**Files:** `frontend/app/page.tsx`, `frontend/app/prompter.tsx`, `frontend/app/globals.css`, `frontend/tests/`

**Changes:**
- Add `usePauseDetection(amplitude, threshold=0.05, durationMs=1200)` hook in `page.tsx`
  - Tracks `lastSpeechAt` ref via `useEffect` on amplitude
  - Returns `isPaused: boolean`
- Pass `isPaused` as prop to `<Prompter />`
- In `Prompter`: render prediction with two CSS classes — `prediction-word--dim` (speaking) and `prediction-word--prominent` (paused)
- In `globals.css`: define both states and the `prediction-fadeout` class for resume

**CSS states:**

```css
.prediction-word--dim {
  font-size: 0.9rem;
  opacity: 0.25;
  transition: none;
}

.prediction-word--prominent {
  font-size: clamp(3rem, 8vw, 5rem);
  font-weight: 700;
  opacity: 1;
  animation: fadeSlideUp 180ms ease-out;
}

.prediction-word--fadeout {
  opacity: 0;
  transition: opacity 500ms ease;
}
```

**Tests (Vitest):**
- `isPaused` is false when amplitude stays above threshold
- `isPaused` becomes true after 1.2s of amplitude below threshold
- `isPaused` resets when amplitude rises
- Prompter renders `prediction-word--dim` during speech
- Prompter renders `prediction-word--prominent` on pause
- Prompter applies `prediction-word--fadeout` on resume

---

### WS2 — Prediction quality (`feature/prediction-quality`)

**Files:** `backend/routes/routes.py`, `backend/tests/test_llm_predictions.py`

**Changes to `stream_llm_prediction`:**

Transcript context window:
```python
recent_transcript = " ".join(transcript_text.split()[-30:])
```

New system prompt:
```
You are a real-time speech coach. A speaker has frozen mid-sentence and needs a nudge.

Predict the next 1–3 words that satisfy BOTH conditions:
1. Natural grammatical continuation of the last words spoken
2. Relevant to the speaker's topic and domain from their context notes

Rules:
- Use 1 word if the continuation is unambiguous
- Use 2–3 words if more specificity helps orient the speaker
- Never repeat the last word spoken
- Stay within the domain described in the context notes
- Output ONLY the words — no punctuation, no explanation, no quotes
```

New user message:
```
Speaker's domain and topic (this is the scope — stay within it):
{context or "(none)"}

Last words spoken:
{last 30 words of transcript or "(none)"}

Continue (1–3 words):
```

Temperature: `0.4 → 0.2`

**Tests (pytest):**
- System prompt contains "grammatical" and "domain"
- System prompt contains "never repeat the last word"
- System prompt contains "1" and "3"
- User message passes last-30-words window (not full transcript)
- `temperature=0.2` asserted
- `max_tokens=12` asserted

---

### WS3 — Latency profiling (`feature/latency-profiling`)

**Files:** `backend/routes/routes.py`, `frontend/components/recorder.tsx`

**Changes:**
- Backend: add `prediction_start_ms` timestamp when `stream_llm_prediction` fires; emit `prediction_ms` in first predictions event
- Frontend: log `[latency] prediction_ms=X` to console when first predictions event arrives
- Backend: add structured log line `prediction_ttft_ms=X` (time to first token from Claude)

**Goal:** establish baseline latency numbers before and after WS2 lands. No user-facing changes.

---

### WS4 — Prediction test suite (`feature/prediction-test-suite`)

**Files:** `backend/tests/test_prediction_quality.py` (new)

**Tests:**
- Quality gate: given a realistic transcript + context, Claude mock returns 1–3 words, all in domain
- No-repeat gate: prediction does not start with the last spoken word
- Short output gate: prediction is ≤ 3 words
- Fallback gate: bigram fallback fires on Claude error and returns something sensible
- Latency budget: mocked stream completes prediction task within 2s

---

## Testing Summary

| Layer | Framework | Count target |
|---|---|---|
| Pause detection (frontend) | Vitest | 6 new tests |
| Prediction quality (backend) | pytest | 6 new tests |
| Prediction quality suite (backend) | pytest | 5 new tests |
| Latency profiling (backend) | pytest | 2 new tests |

All existing 73 backend + 37 frontend tests must remain green.

---

## Success Criteria

1. Speaker speaks → prediction is present but invisible (dim, small)
2. Speaker pauses 1.2s → prediction animates to full size instantly (no Claude wait)
3. Prediction is 1–3 words, domain-relevant, grammatically correct continuation
4. Speaker resumes → prediction fades over 0.5s
5. All 110 existing tests + 19 new tests pass
6. Console latency logs show Claude TTFT < 1s on a normal connection
