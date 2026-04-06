# WS2: Prediction Quality — Prompt + Context Window

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rewrite the Claude prompt to require both grammatical continuation and domain relevance, narrow transcript context to the last 30 words, and drop temperature to 0.2.

**Architecture:** Single function change in `stream_llm_prediction` in `backend/routes/routes.py`. The new system prompt makes both conditions (grammar + domain) explicit with rules. Transcript window is sliced to 30 words before passing to Claude. Temperature drops from 0.4 to 0.2 for more reliable completions.

**Tech Stack:** Python 3.11, pytest, pytest-asyncio, unittest.mock, Anthropic SDK

**GitHub Issue:** #35
**Branch:** `feature/prediction-quality`
**Depends on:** WS4 (#36) must be merged first — quality tests provide the gate

---

## File Map

| Action | File | Responsibility |
|---|---|---|
| Modify | `backend/routes/routes.py` — update `stream_llm_prediction`: new prompt, 30-word window, temperature=0.2 |
| Modify | `backend/tests/test_llm_predictions.py` — 6 new assertion tests |

---

### Task 1: Branch setup

- [ ] **Step 1: Create branch from latest main (after WS4 is merged)**

```bash
git fetch origin && git checkout main && git pull origin main
git checkout -b feature/prediction-quality
```

- [ ] **Step 2: Confirm all existing tests pass (should include WS4's 5 tests)**

```bash
cd backend
env/bin/pytest tests/ -v
```

Expected: `78 passed` (73 + 5 from WS4)

---

### Task 2: Write failing tests for the new prompt

- [ ] **Step 1: Open `backend/tests/test_llm_predictions.py` and add 6 new tests at the bottom**

These tests capture the kwargs passed to `_anthropic_client.messages.stream` and assert on their values.

```python
# ---------------------------------------------------------------------------
# WS2: New prompt assertions
# ---------------------------------------------------------------------------

def make_capturing_ctx(captured: dict):
    """Helper that captures kwargs passed to messages.stream and yields a mock stream."""
    @asynccontextmanager
    async def _ctx(**kwargs):
        captured.update(kwargs)
        mock_stream = MagicMock()
        mock_stream.text_stream = make_async_text_stream(["next"])
        yield mock_stream
    return _ctx


@pytest.mark.asyncio
async def test_prompt_requires_grammatical_continuation(sid):
    """System prompt explicitly requires grammatical continuation."""
    captured = {}
    mock_client = MagicMock()
    mock_client.messages.stream = MagicMock(side_effect=lambda **kw: make_capturing_ctx(captured)(**kw))

    with patch.object(routes_module, "_anthropic_client", mock_client), \
         patch("routes.routes.sio") as mock_sio:
        mock_sio.emit = AsyncMock()
        await stream_llm_prediction(sid, "tech podcast", "the main thing about")

    system = captured.get("system", "")
    assert "grammatical" in system.lower(), f"prompt missing 'grammatical': {system[:200]}"


@pytest.mark.asyncio
async def test_prompt_requires_domain_relevance(sid):
    """System prompt explicitly requires domain relevance."""
    captured = {}
    mock_client = MagicMock()
    mock_client.messages.stream = MagicMock(side_effect=lambda **kw: make_capturing_ctx(captured)(**kw))

    with patch.object(routes_module, "_anthropic_client", mock_client), \
         patch("routes.routes.sio") as mock_sio:
        mock_sio.emit = AsyncMock()
        await stream_llm_prediction(sid, "tech podcast", "the main thing about")

    system = captured.get("system", "")
    assert "domain" in system.lower() or "topic" in system.lower(), \
        f"prompt missing domain/topic requirement: {system[:200]}"


@pytest.mark.asyncio
async def test_prompt_includes_no_repeat_rule(sid):
    """System prompt tells Claude never to repeat the last spoken word."""
    captured = {}
    mock_client = MagicMock()
    mock_client.messages.stream = MagicMock(side_effect=lambda **kw: make_capturing_ctx(captured)(**kw))

    with patch.object(routes_module, "_anthropic_client", mock_client), \
         patch("routes.routes.sio") as mock_sio:
        mock_sio.emit = AsyncMock()
        await stream_llm_prediction(sid, "context", "some transcript")

    system = captured.get("system", "")
    assert "repeat" in system.lower(), f"prompt missing no-repeat rule: {system[:200]}"


@pytest.mark.asyncio
async def test_transcript_window_capped_at_30_words(sid):
    """Only the last 30 words of transcript are passed to Claude."""
    captured = {}
    mock_client = MagicMock()
    mock_client.messages.stream = MagicMock(side_effect=lambda **kw: make_capturing_ctx(captured)(**kw))

    # Build a transcript longer than 30 words
    long_transcript = " ".join([f"word{i}" for i in range(50)])  # 50 words

    with patch.object(routes_module, "_anthropic_client", mock_client), \
         patch("routes.routes.sio") as mock_sio:
        mock_sio.emit = AsyncMock()
        await stream_llm_prediction(sid, "context", long_transcript)

    user_content = captured.get("messages", [{}])[0].get("content", "")
    # The first 20 words (word0..word19) should NOT appear in the user message
    assert "word0" not in user_content, "full transcript passed — should be last 30 words only"
    assert "word49" in user_content, "last word of transcript missing from user message"


@pytest.mark.asyncio
async def test_temperature_is_0_point_2(sid):
    """Claude is called with temperature=0.2."""
    captured = {}
    mock_client = MagicMock()
    mock_client.messages.stream = MagicMock(side_effect=lambda **kw: make_capturing_ctx(captured)(**kw))

    with patch.object(routes_module, "_anthropic_client", mock_client), \
         patch("routes.routes.sio") as mock_sio:
        mock_sio.emit = AsyncMock()
        await stream_llm_prediction(sid, "context", "some transcript")

    assert captured.get("temperature") == 0.2, \
        f"expected temperature=0.2, got {captured.get('temperature')}"


@pytest.mark.asyncio
async def test_max_tokens_still_12(sid):
    """max_tokens remains 12 after prompt update."""
    captured = {}
    mock_client = MagicMock()
    mock_client.messages.stream = MagicMock(side_effect=lambda **kw: make_capturing_ctx(captured)(**kw))

    with patch.object(routes_module, "_anthropic_client", mock_client), \
         patch("routes.routes.sio") as mock_sio:
        mock_sio.emit = AsyncMock()
        await stream_llm_prediction(sid, "context", "some transcript")

    assert captured.get("max_tokens") == 12
```

- [ ] **Step 2: Run to confirm new tests fail**

```bash
env/bin/pytest tests/test_llm_predictions.py -v -k "grammatical or domain_relevance or no_repeat_rule or window_capped or temperature or max_tokens_still"
```

Expected: all 6 FAIL (current prompt doesn't satisfy these assertions)

---

### Task 3: Implement the new prompt and context window

- [ ] **Step 1: Open `backend/routes/routes.py` and replace the `system_prompt` and `user_message` in `stream_llm_prediction`**

Find the current values (around lines 141–153) and replace:

```python
    system_prompt = (
        "You are a real-time speech coach. A speaker has frozen mid-sentence and needs a nudge.\n\n"
        "Predict the next 1–3 words that satisfy BOTH conditions:\n"
        "1. Natural grammatical continuation of the last words spoken\n"
        "2. Relevant to the speaker's topic and domain from their context notes\n\n"
        "Rules:\n"
        "- Use 1 word if the continuation is unambiguous\n"
        "- Use 2–3 words if more specificity helps orient the speaker\n"
        "- Never repeat the last word spoken\n"
        "- Stay within the domain described in the context notes\n"
        "- Output ONLY the words — no punctuation, no explanation, no quotes"
    )

    recent_transcript = " ".join(transcript_text.split()[-30:]) if transcript_text else ""

    user_message = (
        f"Speaker's domain and topic (this is the scope — stay within it):\n{context or '(none)'}\n\n"
        f"Last words spoken:\n{recent_transcript or '(none)'}\n\n"
        "Continue (1–3 words):"
    )
```

- [ ] **Step 2: Update `temperature` from 0.4 to 0.2**

Find:
```python
            temperature=0.4,
```

Change to:
```python
            temperature=0.2,
```

- [ ] **Step 3: Run the 6 new tests**

```bash
env/bin/pytest tests/test_llm_predictions.py -v -k "grammatical or domain_relevance or no_repeat_rule or window_capped or temperature or max_tokens_still"
```

Expected: all 6 PASS

---

### Task 4: Run full backend suite

- [ ] **Step 1: Run all tests**

```bash
env/bin/pytest tests/ -v
```

Expected: `84 passed` (78 after WS4 + 6 new)

---

### Task 5: Commit and push

- [ ] **Step 1: Commit**

```bash
git add backend/routes/routes.py backend/tests/test_llm_predictions.py
git commit -m "feat: prediction quality — new prompt, 30-word window, temperature 0.2

New system prompt explicitly requires both grammatical continuation
and domain relevance. Transcript narrowed to last 30 words. Temperature
dropped from 0.4 to 0.2 for more reliable completions.

Closes #35
Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

- [ ] **Step 2: Push and open PR**

```bash
git push -u origin feature/prediction-quality
gh pr create --title "feat: prediction quality — prompt, context window, temperature" \
  --body "Rewritten prompt requires grammatical + domain-relevant continuations. Last 30 words only. temperature=0.2. Closes #35."
```
