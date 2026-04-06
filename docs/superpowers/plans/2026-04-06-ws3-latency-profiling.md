# WS3: Latency Profiling

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Instrument the prediction pipeline so every Claude request emits structured latency data — TTFT (time to first token) and total prediction duration — visible in both server logs and the browser console.

**Architecture:** Backend records `prediction_start_ms` when `stream_llm_prediction` fires and emits `prediction_ms` alongside the first `predictions` event. Frontend logs it on receipt. No user-facing UI changes.

**Tech Stack:** Python 3.11, pytest, pytest-asyncio, TypeScript, Socket.IO

**GitHub Issue:** #37
**Branch:** `feature/latency-profiling`
**Independent of:** WS1, WS2, WS4

---

## File Map

| Action | File | Responsibility |
|---|---|---|
| Modify | `backend/routes/routes.py` — record `prediction_start_ms`, emit `prediction_ms` in first predictions event, structured log `prediction_ttft_ms` |
| Modify | `frontend/components/recorder.tsx` — log `[latency] prediction_ms=X` on predictions event |
| Modify | `backend/tests/test_llm_predictions.py` — 2 new tests asserting timing fields |

---

### Task 1: Branch setup

- [ ] **Step 1: Create branch from latest main**

```bash
git fetch origin && git checkout main && git pull origin main
git checkout -b feature/latency-profiling
```

- [ ] **Step 2: Confirm all existing tests pass**

```bash
cd backend && env/bin/pytest tests/ -v
```

Expected: `73 passed` (or more if WS4 is already merged)

---

### Task 2: Write failing latency tests

- [ ] **Step 1: Open `backend/tests/test_llm_predictions.py` and add 2 tests at the bottom**

```python
# ---------------------------------------------------------------------------
# WS3: Latency profiling — timing fields in predictions payload
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_first_predictions_event_includes_prediction_ms(sid):
    """The first predictions event includes a prediction_ms timing field."""
    tokens = ["next", " step"]
    first_payload = {}

    async def capture(event, data, **_):
        if event == "predictions" and not first_payload:
            first_payload.update(data)

    mock_client = MagicMock()
    mock_client.messages.stream = MagicMock(return_value=make_stream_ctx(tokens))

    with (
        patch.object(routes_module, "_anthropic_client", mock_client),
        patch("routes.routes.sio") as mock_sio,
    ):
        mock_sio.emit = capture
        await stream_llm_prediction(sid, "context", "transcript here")

    assert "prediction_ms" in first_payload, (
        f"prediction_ms missing from first predictions payload: {first_payload}"
    )
    assert isinstance(first_payload["prediction_ms"], (int, float))
    assert first_payload["prediction_ms"] >= 0


@pytest.mark.asyncio
async def test_subsequent_predictions_events_omit_prediction_ms(sid):
    """Only the first predictions event carries prediction_ms — subsequent ones do not."""
    tokens = ["a", " b", " c"]
    all_payloads = []

    async def capture(event, data, **_):
        if event == "predictions":
            all_payloads.append(dict(data))

    mock_client = MagicMock()
    mock_client.messages.stream = MagicMock(return_value=make_stream_ctx(tokens))

    with (
        patch.object(routes_module, "_anthropic_client", mock_client),
        patch("routes.routes.sio") as mock_sio,
    ):
        mock_sio.emit = capture
        await stream_llm_prediction(sid, "context", "transcript")

    assert len(all_payloads) >= 2, "need at least 2 emit calls to test this"
    # First has prediction_ms
    assert "prediction_ms" in all_payloads[0]
    # Rest do not
    for payload in all_payloads[1:]:
        assert "prediction_ms" not in payload, (
            f"subsequent payload should not have prediction_ms: {payload}"
        )
```

- [ ] **Step 2: Run to confirm they fail**

```bash
env/bin/pytest tests/test_llm_predictions.py -v -k "prediction_ms"
```

Expected: both FAIL (`prediction_ms` key not in payload yet)

---

### Task 3: Instrument `stream_llm_prediction` in `routes.py`

- [ ] **Step 1: Add timing instrumentation to the function**

In `stream_llm_prediction`, find the line `accumulated = ""` and add the start timer just before the `async with` block:

```python
    accumulated = ""
    prediction_start = time.perf_counter()
    first_token = True
    try:
        async with _anthropic_client.messages.stream(
            ...
        ) as stream:
            async for text_delta in stream.text_stream:
                accumulated = (accumulated + text_delta).strip()
                words = accumulated.split()
                if len(words) > MAX_PREDICTION_WORDS:
                    accumulated = " ".join(words[:MAX_PREDICTION_WORDS])
                    payload: dict = {"items": [accumulated]}
                    if first_token:
                        ttft_ms = round((time.perf_counter() - prediction_start) * 1000)
                        payload["prediction_ms"] = ttft_ms
                        logger.info("prediction_ttft_ms=%d sid=%s", ttft_ms, sid)
                        first_token = False
                    await sio.emit("predictions", payload, room=sid)
                    break
                if accumulated:
                    payload = {"items": [accumulated]}
                    if first_token:
                        ttft_ms = round((time.perf_counter() - prediction_start) * 1000)
                        payload["prediction_ms"] = ttft_ms
                        logger.info("prediction_ttft_ms=%d sid=%s", ttft_ms, sid)
                        first_token = False
                    await sio.emit("predictions", payload, room=sid)
```

**Note:** `time` is already imported at the top of `routes.py`. `logger` is already defined as `logging.getLogger("teleprompt.latency")`.

- [ ] **Step 2: Run the latency tests**

```bash
env/bin/pytest tests/test_llm_predictions.py -v -k "prediction_ms"
```

Expected: both PASS

- [ ] **Step 3: Run full backend suite**

```bash
env/bin/pytest tests/ -v
```

Expected: all tests pass (no regressions)

---

### Task 4: Instrument `recorder.tsx` frontend logging

- [ ] **Step 1: Open `frontend/components/recorder.tsx` and update the predictions handler**

Find:
```typescript
        newSocket.on("predictions", (response: { items?: string[] }) => {
            onPredictions(response?.items ?? []);
        });
```

Replace with:
```typescript
        newSocket.on("predictions", (response: { items?: string[]; prediction_ms?: number }) => {
            if (typeof response?.prediction_ms === "number") {
                console.info(`[latency] prediction_ttft_ms=${response.prediction_ms}`);
            }
            onPredictions(response?.items ?? []);
        });
```

- [ ] **Step 2: No frontend test needed** — this is a console.info call; verify manually in browser DevTools after deployment.

---

### Task 5: Commit and push

- [ ] **Step 1: Commit**

```bash
git add backend/routes/routes.py backend/tests/test_llm_predictions.py \
        frontend/components/recorder.tsx
git commit -m "feat: latency profiling for prediction pipeline

Backend emits prediction_ms (time to first Claude token) in the first
predictions event and logs prediction_ttft_ms to the latency logger.
Frontend logs [latency] prediction_ttft_ms=X to browser console.

Closes #37
Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

- [ ] **Step 2: Push and open PR**

```bash
git push -u origin feature/latency-profiling
gh pr create --title "feat: latency profiling for prediction pipeline" \
  --body "Instruments prediction TTFT in backend logs and browser console. No user-facing changes. Closes #37."
```
