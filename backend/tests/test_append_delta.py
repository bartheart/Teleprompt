"""
Unit tests for append_delta() — overlap-aware transcript concatenation.
"""

import sys
import types

if "faster_whisper" not in sys.modules:
    fw = types.ModuleType("faster_whisper")
    fw.WhisperModel = object  # type: ignore[attr-defined]
    sys.modules["faster_whisper"] = fw

from routes.routes import append_delta


class TestAppendDelta:
    def test_empty_existing_returns_new(self):
        assert append_delta("", "hello world") == "hello world"

    def test_empty_new_returns_empty(self):
        assert append_delta("hello world", "") == ""

    def test_both_empty(self):
        assert append_delta("", "") == ""

    def test_no_overlap_appends_all(self):
        assert append_delta("hello", "world foo") == "world foo"

    def test_full_overlap_returns_empty(self):
        # New text is entirely contained in the tail of existing
        assert append_delta("the quick brown fox", "brown fox") == ""

    def test_partial_overlap_strips_overlap(self):
        result = append_delta("hello world", "world foo bar")
        assert result == "foo bar"

    def test_single_word_overlap(self):
        result = append_delta("one two three", "three four")
        assert result == "four"

    def test_multi_word_overlap(self):
        result = append_delta("a b c d", "c d e f")
        assert result == "e f"

    def test_no_common_words(self):
        result = append_delta("alpha beta", "gamma delta")
        assert result == "gamma delta"

    def test_repeated_words_uses_longest_suffix_overlap(self):
        # "the the" at end, new starts with "the the next" — overlap = 2
        result = append_delta("one the the", "the the next")
        assert result == "next"

    def test_single_word_existing_no_overlap(self):
        assert append_delta("hello", "world") == "world"

    def test_whitespace_handling(self):
        # Extra spaces should not cause index errors
        result = append_delta("hello world", "world  bar")
        # split() normalises whitespace
        assert "bar" in result
