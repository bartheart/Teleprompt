"use client";

import { FormEvent, useMemo, useState } from "react";
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

  return (
    <div>
      <p>LOGO</p>
      <div>
        <form onSubmit={startTeleprompter}>
          <div>
            <label>Context</label>
            <input
              type="text"
              value={context}
              onChange={(event) => setContext(event.target.value)}
              placeholder="Enter talk context (topic, audience, goal)"
            />
          </div>
          <button type="submit" disabled={isActive}>
            Start Teleprompter
          </button>
          <button type="button" onClick={stopTeleprompter} disabled={!isActive}>
            Stop Teleprompter
          </button>
        </form>
      </div>
      <div>
        <Recorder
          context={context}
          predictionCount={predictionCount}
          active={isActive}
          onTranscript={(text) => setTranscripts((prev) => [...prev, text])}
          onPredictions={(items) => setPredictions(items)}
        />
      </div>
      <Prompter transcripts={transcripts} predictions={predictions} />
    </div>
  );
}
