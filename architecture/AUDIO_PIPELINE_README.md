# Audio Data Pipeline README

This document focuses on the realtime audio pipeline, its current architecture, and practical changes to achieve sub-2 second end-to-end turnaround (audio in -> next token out).

## Current Architecture (As Implemented)

### 1) Browser Capture + Chunking
- Web Audio API creates an `AudioContext` at 16 kHz.
- A `ScriptProcessorNode` with a buffer size of 4096 samples emits chunks.
- Each chunk is converted to Int16 PCM and sent over Socket.IO.

**Implications**
- 4096 samples @ 16 kHz ~ 256 ms of audio per chunk.
- Chunking cadence sets the minimum client-side "packet" latency.

### 2) Transport
- Socket.IO over WebSocket, `audio_pcm` event per chunk.
- No explicit compression or batching beyond the 4096-sample buffer.

**Implications**
- Bandwidth is modest, but latency is sensitive to per-chunk overhead and TCP/WebSocket buffering.

### 3) Backend Aggregation + ASR
- Incoming PCM is concatenated into a growing NumPy array.
- Processing triggers only when >= 1 second of new audio is available.
- Whisper transcribes a rolling ~6 second tail window.
- Inference is CPU-bound and runs in the event loop thread via `asyncio.to_thread`.
- While inference is running, new audio events are ignored (`is_processing` gate).

**Implications**
- Base latency includes the 1s aggregation threshold, plus Whisper inference time.
- The `is_processing` guard can drop audio under load, which increases perceived latency and reduces accuracy.

### 4) Output
- Backend emits a `transcription` event and predicted next words.
- UI shows trailing words (last 1-3 tokens).

## Observed Latency Budget (Conceptual)

These are not measured values, but the structural contributors in the current design:
- Client chunking: ~256 ms
- Backend aggregation: ~1000 ms (minimum, by design)
- ASR inference: variable (CPU Whisper)
- Network + scheduling: variable

Even with ideal inference, the 1s aggregation makes sub-2s turnaround difficult.

## Main Tradeoffs in the Current Design

- **Latency vs compute**: 1 second batching reduces inference calls but adds latency.
- **Context vs speed**: 6 second tail window improves recognition but increases inference time.
- **Simplicity vs loss**: `is_processing` drops audio when busy, sacrificing completeness to keep concurrency simple.
- **CPU portability vs throughput**: CPU Whisper is easy to deploy but slower than GPU or optimized runtimes.

## Path to Sub-2s Turnaround

Below is a realistic set of changes to reach < 2s from audio to next token on commodity hardware, and comfortably < 1s on GPU.

### A) Reduce Client Buffer Size and Use AudioWorklet
**Goal:** reduce capture + packet latency from ~256 ms to ~40-80 ms.

- Replace `ScriptProcessorNode` (deprecated) with `AudioWorkletNode`.
- Use smaller buffers (e.g., 512 or 1024 samples).
- Optionally add client-side VAD to avoid sending silence.

**Tradeoff:** higher packet rate increases CPU and network overhead.

### B) Lower Backend Aggregation Threshold
**Goal:** reduce the fixed 1s aggregation delay to 200-400 ms.

- Change `PROCESS_EVERY_SAMPLES` from 16000 to 3200-6400.
- Keep a short overlapping window (1-2 seconds) for context.
- Emit partial results more frequently.

**Tradeoff:** more frequent inference calls can be expensive if using full Whisper.

### C) Use Streaming/Incremental ASR
**Goal:** generate tokens continuously rather than in 1s batches.

Options:
- Switch to a streaming-capable model (Whisper streaming variants, Vosk, Deepgram, etc.).
- Use `faster-whisper` (CTranslate2) with small chunk sizes and partial decoding.
- Use an online VAD + segmenter to drive incremental decoding.

**Tradeoff:** more complex state management, may slightly reduce accuracy vs full-context decode.

### D) Avoid Dropping Audio Under Load
**Goal:** preserve all audio while inference runs.

- Replace `is_processing` with a ring buffer queue.
- If inference is behind, skip decoding older audio but still retain it for continuity.
- Separate ingestion from inference with a worker thread or process.

**Tradeoff:** more memory and complexity; requires backpressure strategy.

### E) Optimize Model and Hardware
**Goal:** reduce inference time well below 500 ms per chunk.

- Use GPU (CUDA) or Apple M-series acceleration.
- Prefer `tiny.en` or `base.en` for latency-critical flows.
- Use `faster-whisper` with int8/float16 on GPU for significant speedups.

**Tradeoff:** infrastructure cost and deployment complexity.

### F) Prediction Pipeline Fast Path
**Goal:** emit next-token suggestions even before full ASR completes.

- Use incremental transcripts to update predictions.
- Avoid waiting for full 6s window to complete.
- If streaming ASR is adopted, tie prediction updates to partial hypotheses.

**Tradeoff:** more frequent updates can be noisy; consider debouncing.

## Example Target Latency Budget (Sub-2s)

This is a feasible target if the changes above are implemented:
- Client chunking: 50-80 ms (AudioWorklet + 1024 samples)
- Backend aggregation: 200-400 ms
- ASR inference: 300-800 ms (optimized CPU) or 100-300 ms (GPU)
- Network/scheduling: 50-150 ms

**Total**: ~700-1,700 ms (sub-2s)

## Suggested Implementation Order

1. Replace `ScriptProcessorNode` with `AudioWorkletNode` and reduce buffer size.
2. Lower `PROCESS_EVERY_SAMPLES` to 3200-6400 and reduce tail window to 2-3s.
3. Replace `is_processing` gating with a ring buffer + worker.
4. Swap Whisper runtime to `faster-whisper` and test int8/float16.
5. Consider streaming ASR if latency targets still unmet.

## Notes on Accuracy vs Latency

Expect a small accuracy drop when reducing context window or using streaming models. If accuracy is critical, a hybrid mode can work:
- Use low-latency partials for UI updates.
- Periodically run a higher-context re-decode to refine the transcript in the background.
