type PrompterProps = {
  transcript: string;
  prediction: string;
};

const WORD_OPACITIES = [0.25, 0.55, 1];

export default function Prompter({ transcript, prediction }: PrompterProps) {
  const words = transcript ? transcript.split(/\s+/).filter(Boolean).slice(-3) : [];

  return (
    <div className="prompter">
      <div className="transcript-row">
        {words.length === 0 ? (
          <span className="transcript-placeholder">Start speaking…</span>
        ) : (
          words.map((word, i) => {
            // align opacities to the right so the last (current) word is always full opacity
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
          <span className="prediction-word" key={prediction}>
            {prediction}
          </span>
        ) : (
          <span className="prediction-placeholder">—</span>
        )}
      </div>
    </div>
  );
}
