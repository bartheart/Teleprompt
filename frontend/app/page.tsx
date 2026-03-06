"use client";

import { FormEvent, useCallback, useMemo, useState } from "react";
import Recorder from "../components/recorder";
import Prompter from "./prompter";

export default function Home() {
  const [context, setContext] = useState("");
  const [isActive, setIsActive] = useState(false);
  const [transcripts, setTranscripts] = useState<string[]>([]);
  const [predictions, setPredictions] = useState<string[]>([]);

  const startTeleprompter = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setTranscripts([]);
    setPredictions([]);
    setIsActive(true);
  };

  const stopTeleprompter = () => {
    setIsActive(false);
  };

  const predictionCount = useMemo(() => 5, []);

  const handleTranscript = useCallback((text: string) => {
    setTranscripts(text ? [text] : []);
  }, []);

  const handlePredictions = useCallback((items: string[]) => {
    setPredictions(items);
  }, []);

  return (
    <div className="app-shell">
      <div className="ambient" aria-hidden="true" />
      <main className="app">
        <header className="header">
          <p className="eyebrow">Realtime Speech Assistant</p>
          <h1>Teleprompt</h1>
          <p className="subhead">Live transcript and phrase prompts for natural delivery.</p>
        </header>

        <div className="layout-grid">
          <section className="panel controls" aria-label="Control panel">
            <h2 className="section-title">Session Setup</h2>
            <form onSubmit={startTeleprompter} className="form-stack">
              <label className="label" htmlFor="context-input">
                Context
              </label>
              <input
                id="context-input"
                className="input"
                type="text"
                value={context}
                onChange={(event) => setContext(event.target.value)}
                placeholder="Audience, topic, and tone"
              />
              <div className="actions">
                <button className="btn btn-primary" type="submit" disabled={isActive}>
                  Start Session
                </button>
                <button
                  className="btn btn-secondary"
                  type="button"
                  onClick={stopTeleprompter}
                  disabled={!isActive}
                >
                  Stop
                </button>
              </div>
            </form>

            <Recorder
              context={context}
              predictionCount={predictionCount}
              active={isActive}
              onTranscript={handleTranscript}
              onPredictions={handlePredictions}
            />
          </section>

          <section className="panel" aria-label="Transcript and predictions">
            <Prompter transcripts={transcripts} predictions={predictions} />
          </section>
        </div>
      </main>
    </div>
  );
}
