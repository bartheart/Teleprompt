# Next-Word Prediction Handoff

## Branch
- `feat/improve-next-word-prediction-v2`

## Scope completed
- Improved prediction quality by combining:
  - transcript n-gram signals,
  - context/topic priors,
  - anti-echo filtering.
- Predictions now return token-like next-word candidates instead of phrase recombinations.

## Remaining work (for tomorrow)
- Tune weighting constants for transcript/context blend.
- Add confidence score per predicted token.
- Reduce generic fallback frequency.
- Add lightweight evaluation prompts for regression checks.
