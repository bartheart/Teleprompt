"use client";

import { FormEvent, useMemo, useState } from "react";
import { useCallback } from "react";
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
    <div className="page-shell">
      <main className="page-card">
        <header className="topbar">
          <div>
            <h1 className="title">Teleprompt MVP</h1>
            <p className="subtitle">Minimal live transcription with next-phrase hints</p>
          </div>
        </header>

        <div className="body-grid">
          <section className="control-panel">
            <form onSubmit={startTeleprompter}>
              <label className="label" htmlFor="context-input">
                Context
              </label>
              <input
                id="context-input"
                className="input"
                type="text"
                value={context}
                onChange={(event) => setContext(event.target.value)}
                placeholder="Talk topic, audience, and desired tone"
              />
              <div className="actions">
                <button className="btn btn-primary" type="submit" disabled={isActive}>
                  Start
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

          <section className="content-panel">
            <Prompter transcripts={transcripts} predictions={predictions} />
          </section>
        </div>
      </main>
    </div>
  );
}
