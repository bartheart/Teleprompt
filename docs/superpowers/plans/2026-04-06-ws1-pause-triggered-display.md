# WS1: Pause-Triggered Prediction Display

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Predictions sit dim + small during speech and animate to full size after 1.2s of silence, fading out in 0.5s when the speaker resumes.

**Architecture:** Amplitude data already flows from `Recorder` → `page.tsx` via `onAmplitude`. A `usePauseDetection` hook in `page.tsx` tracks silence duration using a ref and returns `isPaused: boolean`. This prop flows to `Prompter`, which applies one of three CSS classes. No backend changes, no new Socket.IO events.

**Tech Stack:** React 19, Next.js 15, Vitest, @testing-library/react, CSS custom properties

**GitHub Issue:** #34
**Branch:** `feature/pause-triggered-display`
**Independent of:** WS2, WS3, WS4

---

## File Map

| Action | File | Responsibility |
|---|---|---|
| Modify | `frontend/app/page.tsx` | Add `usePauseDetection` hook, pass `isPaused` to `Prompter` |
| Modify | `frontend/app/prompter.tsx` | Accept `isPaused` prop, apply CSS class conditionally |
| Modify | `frontend/app/globals.css` | Add `.prediction-word--dim`, `.prediction-word--prominent`, `.prediction-word--fadeout` |
| Modify | `frontend/tests/prompter.test.tsx` | 4 new display-state tests |
| Modify | `frontend/tests/page.test.tsx` | 2 new pause detection tests |

---

### Task 1: Branch setup

- [ ] **Step 1: Create branch from latest main**

```bash
git fetch origin && git checkout main && git pull origin main
git checkout -b feature/pause-triggered-display
```

- [ ] **Step 2: Confirm all existing tests pass**

```bash
cd frontend && npm test
```

Expected: `37 passed`

---

### Task 2: Add CSS states

- [ ] **Step 1: Open `frontend/app/globals.css` and replace the existing `.prediction-word` and `.prediction-placeholder` rules**

Current:
```css
.prediction-word {
  font-size: clamp(3rem, 8vw, 5rem);
  font-weight: 700;
  letter-spacing: -0.03em;
  color: var(--ink);
  line-height: 1;
  animation: fadeSlideUp 180ms ease-out;
}

.prediction-placeholder {
  font-size: clamp(3rem, 8vw, 5rem);
  font-weight: 700;
  color: var(--ink-dim);
  line-height: 1;
}
```

New (replace both with):
```css
/* base shared styles */
.prediction-word {
  font-weight: 700;
  letter-spacing: -0.03em;
  color: var(--ink);
  line-height: 1;
}

/* dim state: visible but unobtrusive during speech */
.prediction-word--dim {
  font-size: 0.9rem;
  opacity: 0.25;
  transition: opacity 200ms ease, font-size 200ms ease;
}

/* prominent state: full size when speaker has blanked */
.prediction-word--prominent {
  font-size: clamp(3rem, 8vw, 5rem);
  opacity: 1;
  animation: fadeSlideUp 180ms ease-out;
}

/* fadeout state: applied when speaker resumes */
.prediction-word--fadeout {
  font-size: 0.9rem;
  opacity: 0;
  transition: opacity 500ms ease, font-size 300ms ease;
}

.prediction-placeholder {
  font-size: clamp(3rem, 8vw, 5rem);
  font-weight: 700;
  color: var(--ink-dim);
  line-height: 1;
}
```

- [ ] **Step 2: No test needed — CSS is verified visually and by the component tests below**

---

### Task 3: Write failing Prompter display-state tests

- [ ] **Step 1: Open `frontend/tests/prompter.test.tsx` and add 4 new tests at the bottom**

First check the existing import block — it should already import `render`, `screen` from `@testing-library/react` and `Prompter`. Add the new tests:

```tsx
// ---------------------------------------------------------------------------
// Pause-state display tests
// ---------------------------------------------------------------------------

describe("Prompter — pause display states", () => {
  it("applies prediction-word--dim class during speech (isPaused=false)", () => {
    render(<Prompter transcript="hello world" prediction="next step" isPaused={false} />);
    const el = screen.getByText("next step");
    expect(el).toHaveClass("prediction-word--dim");
    expect(el).not.toHaveClass("prediction-word--prominent");
  });

  it("applies prediction-word--prominent class when paused (isPaused=true)", () => {
    render(<Prompter transcript="hello world" prediction="next step" isPaused={true} />);
    const el = screen.getByText("next step");
    expect(el).toHaveClass("prediction-word--prominent");
    expect(el).not.toHaveClass("prediction-word--dim");
  });

  it("shows placeholder when prediction is empty regardless of pause state", () => {
    render(<Prompter transcript="hello" prediction="" isPaused={true} />);
    expect(screen.getByText("—")).toBeInTheDocument();
  });

  it("uses stable key so element does not remount on text change", () => {
    const { rerender } = render(
      <Prompter transcript="hello" prediction="the" isPaused={true} />
    );
    const firstEl = screen.getByText("the");
    rerender(<Prompter transcript="hello world" prediction="the next" isPaused={true} />);
    const secondEl = screen.getByText("the next");
    // Both renders hit the same DOM node (stable key="prediction")
    expect(firstEl.tagName).toBe(secondEl.tagName);
  });
});
```

- [ ] **Step 2: Run to confirm they fail**

```bash
cd frontend && npm test -- tests/prompter.test.tsx
```

Expected: 4 new tests FAIL (`isPaused` prop not accepted yet)

---

### Task 4: Update `Prompter` component

- [ ] **Step 1: Update `frontend/app/prompter.tsx`**

```tsx
type PrompterProps = {
  transcript: string;
  prediction: string;
  isPaused: boolean;
};

const WORD_OPACITIES = [0.25, 0.55, 1];

export default function Prompter({ transcript, prediction, isPaused }: PrompterProps) {
  const words = transcript ? transcript.split(/\s+/).filter(Boolean).slice(-3) : [];

  const predictionClass = isPaused ? "prediction-word--prominent" : "prediction-word--dim";

  return (
    <div className="prompter">
      <div className="transcript-row">
        {words.length === 0 ? (
          <span className="transcript-placeholder">Start speaking…</span>
        ) : (
          words.map((word, i) => {
            const opacityIndex = WORD_OPACITIES.length - words.length + i;
            return (
              <span
                key={`${word}-${i}`}
                className="transcript-word"
                style={{ opacity: WORD_OPACITIES[opacityIndex] }}
              >
                {word}
              </span>
            );
          })
        )}
      </div>

      <div className="prediction-row">
        {prediction ? (
          <span className={`prediction-word ${predictionClass}`} key="prediction">
            {prediction}
          </span>
        ) : (
          <span className="prediction-placeholder">—</span>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Run Prompter tests**

```bash
npm test -- tests/prompter.test.tsx
```

Expected: all Prompter tests pass (11 existing + 4 new = 15)

---

### Task 5: Write failing pause detection tests in page.test.tsx

- [ ] **Step 1: Add pause detection tests to `frontend/tests/page.test.tsx`**

Add at the bottom of the file, inside a new describe block. The `Recorder` is already mocked in this file — find the mock and its `onAmplitude` capture pattern.

Add after existing tests:

```tsx
describe("Home — pause detection", () => {
  it("prediction is dim (not paused) immediately after starting", async () => {
    render(<Home />);
    fireEvent.click(screen.getByText("Start Teleprompter"));
    await waitFor(() => screen.getByText("Stop Listening"));

    // Simulate amplitude above threshold — speaker is talking
    const recorderProps = (Recorder as jest.Mock).mock.calls.at(-1)[0];
    act(() => recorderProps.onAmplitude(0.8));

    // prediction-word--dim should be applied (not prominent)
    // We check via Prompter mock — find isPaused=false in its call args
    const prompterCalls = (Prompter as jest.Mock).mock.calls;
    const lastCall = prompterCalls.at(-1)?.[0];
    expect(lastCall?.isPaused).toBe(false);
  });

  it("isPaused becomes true after 1.2s of low amplitude", async () => {
    jest.useFakeTimers();
    render(<Home />);
    fireEvent.click(screen.getByText("Start Teleprompter"));
    await waitFor(() => screen.getByText("Stop Listening"));

    const recorderProps = (Recorder as jest.Mock).mock.calls.at(-1)[0];

    // Send low amplitude (below threshold 0.05)
    act(() => recorderProps.onAmplitude(0.01));

    // Advance time past pause threshold
    act(() => jest.advanceTimersByTime(1300));

    const prompterCalls = (Prompter as jest.Mock).mock.calls;
    const lastCall = prompterCalls.at(-1)?.[0];
    expect(lastCall?.isPaused).toBe(true);

    jest.useRealTimers();
  });
});
```

**Note:** These tests require `Prompter` to be mocked in the test file. If it isn't already, add this to the mock setup section at the top of `page.test.tsx`:

```tsx
jest.mock("../app/prompter", () => ({
  __esModule: true,
  default: jest.fn(() => <div data-testid="prompter" />),
}));
import Prompter from "../app/prompter";
```

- [ ] **Step 2: Run to confirm they fail**

```bash
npm test -- tests/page.test.tsx
```

Expected: 2 new tests FAIL (`isPaused` not implemented yet)

---

### Task 6: Add `usePauseDetection` hook to `page.tsx`

- [ ] **Step 1: Open `frontend/app/page.tsx` and add the hook after existing state declarations**

Add these constants near the top of the `Home` component (after imports):

```tsx
const PAUSE_AMPLITUDE_THRESHOLD = 0.05;
const PAUSE_DURATION_MS = 1200;
const RESUME_FADEOUT_MS = 500;
```

Add inside the `Home` function, after `const smoothedAmpRef = useRef(0);`:

```tsx
const [isPaused, setIsPaused] = useState(false);
const lastSpeechAtRef = useRef<number>(Date.now());
const pauseTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
```

- [ ] **Step 2: Update `handleAmplitude` to drive pause detection**

Current `handleAmplitude`:
```tsx
const handleAmplitude = useCallback((raw: number) => {
  smoothedAmpRef.current = smoothedAmpRef.current * 0.65 + raw * 0.35;
  setAmplitude(smoothedAmpRef.current);
}, []);
```

New `handleAmplitude`:
```tsx
const handleAmplitude = useCallback((raw: number) => {
  smoothedAmpRef.current = smoothedAmpRef.current * 0.65 + raw * 0.35;
  setAmplitude(smoothedAmpRef.current);

  const smoothed = smoothedAmpRef.current;

  if (smoothed > PAUSE_AMPLITUDE_THRESHOLD) {
    // Speaker is talking — record time and clear any pending pause timer
    lastSpeechAtRef.current = Date.now();
    if (pauseTimerRef.current) {
      clearTimeout(pauseTimerRef.current);
      pauseTimerRef.current = null;
    }
    // If we were paused, start fade-out
    setIsPaused((prev) => {
      if (prev) {
        // Schedule reset after fade-out duration
        setTimeout(() => setIsPaused(false), RESUME_FADEOUT_MS);
      }
      return prev; // keep true during fade-out; CSS handles visual
    });
  } else {
    // Below threshold — start/reset pause timer if not already paused
    if (!pauseTimerRef.current) {
      pauseTimerRef.current = setTimeout(() => {
        setIsPaused(true);
        pauseTimerRef.current = null;
      }, PAUSE_DURATION_MS);
    }
  }
}, []);
```

- [ ] **Step 3: Clean up timer on stop**

Update `handleStop`:
```tsx
const handleStop = useCallback(() => {
  setIsActive(false);
  setAmplitude(0);
  smoothedAmpRef.current = 0;
  setIsPaused(false);
  if (pauseTimerRef.current) {
    clearTimeout(pauseTimerRef.current);
    pauseTimerRef.current = null;
  }
}, []);
```

- [ ] **Step 4: Pass `isPaused` to `<Prompter />`**

Find the `<Prompter>` usage in the active screen return:

```tsx
<Prompter transcript={transcript} prediction={predictions[0] ?? ""} isPaused={isPaused} />
```

- [ ] **Step 5: Run page tests**

```bash
npm test -- tests/page.test.tsx
```

Expected: all page tests pass (19 existing + 2 new = 21)

---

### Task 7: Run full frontend suite

- [ ] **Step 1: Run all frontend tests**

```bash
npm test
```

Expected: `43 passed` (37 existing + 6 new)

- [ ] **Step 2: Run lint**

```bash
npm run lint
```

Expected: no errors

---

### Task 8: Commit and push

- [ ] **Step 1: Commit**

```bash
git add frontend/app/page.tsx frontend/app/prompter.tsx frontend/app/globals.css \
        frontend/tests/prompter.test.tsx frontend/tests/page.test.tsx
git commit -m "feat: pause-triggered prediction display

Prediction sits dim (0.9rem, 25% opacity) during speech and animates
to full size after 1.2s of silence. Fades out in 0.5s when speaker resumes.
Pause detection is amplitude-based on the frontend — no backend changes.

Closes #34
Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

- [ ] **Step 2: Push and open PR**

```bash
git push -u origin feature/pause-triggered-display
gh pr create --title "feat: pause-triggered prediction display" \
  --body "Hybrid display: dim during speech, prominent on 1.2s pause, 0.5s fade-out on resume. Closes #34."
```
