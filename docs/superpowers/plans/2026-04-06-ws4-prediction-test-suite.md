# WS4: Prediction Quality Test Suite + Enforcement

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add quality enforcement (max 3-word trim, no-repeat guard) to `stream_llm_prediction` and establish a test suite that validates prediction quality constraints.

**Architecture:** Two changes to `routes/routes.py` — trim accumulated output to 3 words mid-stream and skip predictions that repeat the last spoken word. New test file `backend/tests/test_prediction_quality.py` covers both guards and fallback behaviour.

**Tech Stack:** Python 3.11, pytest, pytest-asyncio, unittest.mock, faster-whisper stub

**GitHub Issue:** #36
**Branch:** `feature/prediction-test-suite`
**Must land before:** WS2 (#35)

---

## File Map

| Action | File |
|---|---|
| Modify | `backend/routes/routes.py` — add 3-word trim + no-repeat guard in `stream_llm_prediction` |
| Create | `backend/tests/test_prediction_quality.py` |

---

### Task 1: Branch setup

- [ ] **Step 1: Create branch from latest main**

```bash
cd /path/to/Teleprompt
git fetch origin && git checkout main && git pull origin main
git checkout -b feature/prediction-test-suite
```

- [ ] **Step 2: Confirm all existing tests pass**

```bash
cd backend
env/bin/pytest tests/ -v
```

Expected: `73 passed`

---

### Task 2: Write failing tests for 3-word trim guard

- [ ] **Step 1: Create test file with helpers**

Create `backend/tests/test_prediction_quality.py`:

```python
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

    assert len(emitted[-1].split()) <= 3


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
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd backend
env/bin/pytest tests/test_prediction_quality.py -v
```

Expected: `test_prediction_trimmed_to_three_words` and `test_no_repeat_guard_replaces_with_fallback` FAIL. Others should pass already.

---

### Task 3: Implement 3-word trim guard in `stream_llm_prediction`

- [ ] **Step 1: Open `backend/routes/routes.py` and locate the streaming loop**

Find the `async for text_delta in stream.text_stream:` block (around line 163).

- [ ] **Step 2: Add `MAX_PREDICTION_WORDS` constant near the top of the file (after existing constants)**

```python
MAX_PREDICTION_WORDS = 3
```

- [ ] **Step 3: Replace the streaming loop with trim-aware version**

Current code:
```python
async for text_delta in stream.text_stream:
    accumulated = (accumulated + text_delta).strip()
    if accumulated:
        await sio.emit("predictions", {"items": [accumulated]}, room=sid)
```

New code:
```python
async for text_delta in stream.text_stream:
    accumulated = (accumulated + text_delta).strip()
    words = accumulated.split()
    if len(words) > MAX_PREDICTION_WORDS:
        accumulated = " ".join(words[:MAX_PREDICTION_WORDS])
        await sio.emit("predictions", {"items": [accumulated]}, room=sid)
        break
    if accumulated:
        await sio.emit("predictions", {"items": [accumulated]}, room=sid)
```

- [ ] **Step 4: Run the trim test to confirm it passes**

```bash
env/bin/pytest tests/test_prediction_quality.py::test_prediction_trimmed_to_three_words -v
```

Expected: PASS

---

### Task 4: Implement no-repeat guard

- [ ] **Step 1: Add no-repeat check after the streaming block in `stream_llm_prediction`**

Find the code immediately after the `async with _anthropic_client.messages.stream(...)` block ends and before the empty-check. Add:

```python
        # No-repeat guard: if prediction starts with the last spoken word, replace with fallback
        if accumulated:
            last_spoken = transcript_text.strip().split()[-1].lower() if transcript_text.strip() else ""
            if last_spoken and accumulated.lower().startswith(last_spoken):
                accumulated = ""  # will trigger fallback below
```

Place this AFTER the stream loop exits but BEFORE the empty check:
```python
        if not accumulated:
            fallback = _bigram_fallback(context, transcript_text, 1)
            if fallback:
                await sio.emit("predictions", {"items": fallback}, room=sid)
```

- [ ] **Step 2: Run the no-repeat test**

```bash
env/bin/pytest tests/test_prediction_quality.py::test_no_repeat_guard_replaces_with_fallback -v
```

Expected: PASS

---

### Task 5: Run full quality suite + full backend suite

- [ ] **Step 1: Run quality suite**

```bash
env/bin/pytest tests/test_prediction_quality.py -v
```

Expected: `5 passed`

- [ ] **Step 2: Run full backend suite**

```bash
env/bin/pytest tests/ -v
```

Expected: `78 passed` (73 existing + 5 new)

---

### Task 6: Commit and push

- [ ] **Step 1: Commit**

```bash
git add backend/routes/routes.py backend/tests/test_prediction_quality.py
git commit -m "feat: add prediction quality guards and test suite

- Trim Claude output to max 3 words mid-stream
- Replace predictions that repeat the last spoken word with bigram fallback
- New test_prediction_quality.py: 5 quality gate tests

Closes #36
Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

- [ ] **Step 2: Push and open PR**

```bash
git push -u origin feature/prediction-test-suite
gh pr create --title "feat: prediction quality guards + test suite" \
  --body "Adds 3-word trim guard, no-repeat guard, and 5 quality tests. Closes #36. Must merge before WS2."
```
