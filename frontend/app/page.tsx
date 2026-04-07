"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Recorder from "../components/recorder";
import Prompter from "./prompter";

const WAVEFORM_MULTS = [0.5, 0.8, 1.0, 0.8, 0.5];
const BAR_MIN_H = 3;
const BAR_MAX_ADD = 38;

const PAUSE_AMPLITUDE_THRESHOLD = 0.05;
const PAUSE_DURATION_MS = 1200;
const RESUME_FADEOUT_MS = 500;

function Waveform({ amplitude }: { amplitude: number }) {
  return (
    <div className="waveform" aria-hidden="true">
      {WAVEFORM_MULTS.map((m, i) => (
        <div
          key={i}
          className="waveform-bar"
          style={{ height: `${BAR_MIN_H + amplitude * BAR_MAX_ADD * m}px` }}
        />
      ))}
    </div>
  );
}

export default function Home() {
  const [context, setContext] = useState("");
  const [isActive, setIsActive] = useState(false);
  const [transcript, setTranscript] = useState("");
  const [predictions, setPredictions] = useState<string[]>([]);
  const [predictionModel, setPredictionModel] = useState("");
  const [dark, setDark] = useState(false);
  const [amplitude, setAmplitude] = useState(0);
  const smoothedAmpRef = useRef(0);

  const [isPaused, setIsPaused] = useState(false);
  const pauseTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const resumeTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Persist + apply dark mode
  useEffect(() => {
    const saved = localStorage.getItem("tp-theme");
    if (saved === "dark") setDark(true);
  }, []);

  useEffect(() => {
    document.documentElement.dataset.theme = dark ? "dark" : "light";
    localStorage.setItem("tp-theme", dark ? "dark" : "light");
  }, [dark]);

  const predictionCount = useMemo(() => 5, []);

  const handleTranscript = useCallback((text: string) => {
    setTranscript(text);
  }, []);

  const handlePredictions = useCallback((items: string[]) => {
    setPredictions(items);
  }, []);

  const handleAmplitude = useCallback((raw: number) => {
    smoothedAmpRef.current = smoothedAmpRef.current * 0.65 + raw * 0.35;
    setAmplitude(smoothedAmpRef.current);

    const smoothed = smoothedAmpRef.current;

    if (smoothed > PAUSE_AMPLITUDE_THRESHOLD) {
      // Speaker is talking — clear any pending pause timer
      if (pauseTimerRef.current) {
        clearTimeout(pauseTimerRef.current);
        pauseTimerRef.current = null;
      }
      // If we were paused, start fade-out
      setIsPaused((prev) => {
        if (prev && !resumeTimerRef.current) {
          resumeTimerRef.current = setTimeout(() => {
            setIsPaused(false);
            resumeTimerRef.current = null;
          }, RESUME_FADEOUT_MS);
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

  const handleStart = useCallback(() => {
    setTranscript("");
    setPredictions([]);
    setIsActive(true);
  }, []);

  const handleStop = useCallback(() => {
    setIsActive(false);
    setAmplitude(0);
    smoothedAmpRef.current = 0;
    setIsPaused(false);
    if (pauseTimerRef.current) {
      clearTimeout(pauseTimerRef.current);
      pauseTimerRef.current = null;
    }
    if (resumeTimerRef.current) {
      clearTimeout(resumeTimerRef.current);
      resumeTimerRef.current = null;
    }
  }, []);

  const toggleTheme = useCallback(() => setDark((d) => !d), []);

  if (!isActive) {
    return (
      <div className="screen">
        <header className="screen-header">
          <span className="logo">Teleprompt</span>
          <button className="theme-toggle" onClick={toggleTheme} aria-label="Toggle theme">
            {dark ? "☀︎" : "☽"}
          </button>
        </header>

        <div className="setup-body">
          <label className="field-label" htmlFor="ctx">
            Context
          </label>
          <textarea
            id="ctx"
            className="context-input"
            value={context}
            onChange={(e) => setContext(e.target.value)}
            placeholder="Audience, topic, and tone"
          />
          <button className="advanced-link" type="button" disabled>
            Advanced Settings
          </button>
        </div>

        <div className="setup-footer">
          <button className="start-btn" type="button" onClick={handleStart}>
            Start Teleprompter
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="screen">
      <header className="screen-header">
        <span className="logo">Teleprompt</span>
        <button className="theme-toggle" onClick={toggleTheme} aria-label="Toggle theme">
          {dark ? "☀︎" : "☽"}
        </button>
      </header>

      <div className="active-body">
        <Prompter transcript={transcript} prediction={predictions[0] ?? ""} isPaused={isPaused} />
        <Waveform amplitude={amplitude} />
        <button className="stop-btn" type="button" onClick={handleStop}>
          Stop Listening
        </button>
        <div className="status-strip">
          <Recorder
            context={context}
            predictionCount={predictionCount}
            active={isActive}
            onTranscript={handleTranscript}
            onPredictions={handlePredictions}
            onAmplitude={handleAmplitude}
            onPredictionModel={setPredictionModel}
          />
        </div>
      </div>
      {predictionModel && (
        <p className="status-text">
          {predictionModel === "claude-haiku" ? "Powered by Claude" : "Basic predictions"}
        </p>
      )}
    </div>
  );
}
