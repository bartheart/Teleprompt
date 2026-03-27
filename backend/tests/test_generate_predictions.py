"""
Unit tests for generate_predictions() — bigram + context next-word suggestions.
"""

import sys
import types

if "faster_whisper" not in sys.modules:
    fw = types.ModuleType("faster_whisper")
    fw.WhisperModel = object  # type: ignore[attr-defined]
    sys.modules["faster_whisper"] = fw

from routes.routes import generate_predictions


class TestGeneratePredictions:
    # ------------------------------------------------------------------
    # Count enforcement
    # ------------------------------------------------------------------

    def test_returns_requested_count(self):
        result = generate_predictions("", "one two three one two three", count=3)
        assert len(result) == 3

    def test_returns_up_to_count_when_candidates_sparse(self):
        result = generate_predictions("", "hello", count=10)
        assert len(result) <= 10

    def test_count_of_one(self):
        result = generate_predictions("", "the quick brown fox", count=1)
        assert len(result) == 1

    # ------------------------------------------------------------------
    # No transcript — falls back to context words
    # ------------------------------------------------------------------

    def test_empty_transcript_uses_context(self):
        result = generate_predictions("artificial intelligence research", "", count=3)
        # Context words longer than 3 chars should appear
        assert any(w in result for w in ["artificial", "intelligence", "research"])

    def test_empty_transcript_empty_context_returns_fallback(self):
        result = generate_predictions("", "", count=3)
        assert len(result) == 3
        assert all(isinstance(w, str) for w in result)

    def test_context_words_shorter_than_4_excluded(self):
        # "is", "in", "or" are ≤ 3 chars and should not come from context
        result = generate_predictions("is in or", "", count=5)
        # Should fall back to hardcoded words rather than short context words
        assert len(result) > 0

    # ------------------------------------------------------------------
    # Bigram ranking
    # ------------------------------------------------------------------

    def test_bigram_followup_ranked_first(self):
        # "the" → "fox" appears twice; "the" → "cat" appears once
        transcript = "the fox jumped the fox sat the cat"
        result = generate_predictions("", transcript, count=5)
        # "fox" should rank higher than "cat" after "the"
        assert result.index("fox") < result.index("cat")

    def test_no_duplicate_predictions(self):
        result = generate_predictions("context word", "hello world hello world", count=5)
        assert len(result) == len(set(result))

    # ------------------------------------------------------------------
    # Punctuation stripping
    # ------------------------------------------------------------------

    def test_punctuation_stripped_from_transcript(self):
        result = generate_predictions("", "hello, world! foo.", count=3)
        for word in result:
            assert not any(c in word for c in ".,!?;:()[]{}\"'")

    # ------------------------------------------------------------------
    # Context integration
    # ------------------------------------------------------------------

    def test_context_words_fill_remaining_slots(self):
        # Short transcript gives few bigrams; context should fill the rest
        result = generate_predictions("machine learning pipeline", "hello", count=5)
        assert len(result) == 5

    def test_result_contains_only_strings(self):
        result = generate_predictions("some context", "some transcript text", count=5)
        assert all(isinstance(w, str) and w for w in result)
