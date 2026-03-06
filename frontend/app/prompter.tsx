type PrompterProps = {
  transcripts: string[];
  predictions: string[];
};

export default function Prompter({ transcripts, predictions }: PrompterProps) {
  const transcript = transcripts[transcripts.length - 1] ?? "";

  return (
    <div className="prompter-stack">
      <section>
        <h2 className="section-title">Live Transcript</h2>
        <div className="transcript-stage">
          {transcript ? (
            <p className="transcript-line">{transcript}</p>
          ) : (
            <p className="muted">No transcript yet. Start and speak to begin.</p>
          )}
        </div>
      </section>

      <section>
        <h2 className="section-title">Suggested Phrases</h2>
        {predictions.length === 0 ? (
          <p className="muted">No suggestions yet.</p>
        ) : (
          <ul className="suggestion-list">
            {predictions.map((item, index) => (
              <li className="suggestion-pill" key={`${item}-${index}`}>
                {item}
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
