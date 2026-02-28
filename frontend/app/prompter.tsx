type PrompterProps = {
  transcripts: string[];
  predictions: string[];
};

export default function Prompter({ transcripts, predictions }: PrompterProps) {
  return (
    <div>
      <h2>Live Transcript</h2>
      {transcripts.length === 0 ? (
        <p>No transcript yet. Start speaking to see updates.</p>
      ) : (
        <ul>
          {transcripts.slice(-6).map((line, index) => (
            <li key={`${line}-${index}`}>{line}</li>
          ))}
        </ul>
      )}

      <h2>Suggested Next Phrases</h2>
      {predictions.length === 0 ? (
        <p>No suggestions yet.</p>
      ) : (
        <ul>
          {predictions.map((item, index) => (
            <li key={`${item}-${index}`}>{item}</li>
          ))}
        </ul>
      )}
    </div>
  );
}
