type PrompterProps = {
  transcripts: string[];
  predictions: string[];
};

export default function Prompter({ transcripts, predictions }: PrompterProps) {
  return (
    <div className="content-grid">
      <section>
        <h2 className="panel-title">Live Transcript</h2>
        <div className="log-box">
          {transcripts.length === 0 ? (
            <p className="muted">No transcript yet. Start and speak to stream text.</p>
          ) : (
            transcripts.slice(-8).map((line, index) => (
              <p className="line" key={`${line}-${index}`}>
                {line}
              </p>
            ))
          )}
        </div>
      </section>

      <section>
        <h2 className="panel-title">Suggested Phrases</h2>
        {predictions.length === 0 ? (
          <p className="muted">No suggestions yet.</p>
        ) : (
          <ul className="suggestions">
            {predictions.map((item, index) => (
              <li key={`${item}-${index}`}>{item}</li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
