"""Filter helpers used by the download endpoint to honour the
`?hide=spkA,spkB` query parameter."""
from __future__ import annotations

from app.routes.transcripts import _filter_segments, _parse_hide, _unique_speakers


def test_parse_hide_returns_safe_tokens_only():
    out = _parse_hide("A,B, with space, C")
    # "with space" fails the regex; commas split it but the token with a
    # space is dropped.
    assert out == frozenset({"A", "B", "C"})


def test_parse_hide_accepts_typical_pyannote_labels():
    out = _parse_hide("SPEAKER_00,SPEAKER_01,?")
    assert out == frozenset({"SPEAKER_00", "SPEAKER_01", "?"})


def test_parse_hide_empty_string_returns_empty_frozenset():
    assert _parse_hide("") == frozenset()
    assert _parse_hide(", ,  ") == frozenset()


def test_parse_hide_rejects_oversized_tokens():
    out = _parse_hide("A," + "x" * 50 + ",B")  # middle token > 32 chars
    assert out == frozenset({"A", "B"})


def test_filter_segments_removes_listed_speakers():
    payload = {"segments": [
        {"speaker": "A", "text": "alpha"},
        {"speaker": "B", "text": "bravo"},
        {"speaker": "A", "text": "alpha2"},
    ]}
    out = _filter_segments(payload, frozenset({"A"}))
    assert [s["text"] for s in out["segments"]] == ["bravo"]
    # Original payload untouched.
    assert len(payload["segments"]) == 3


def test_filter_segments_empty_hide_returns_same_object():
    payload = {"segments": [{"speaker": "A", "text": "alpha"}]}
    assert _filter_segments(payload, frozenset()) is payload


def test_filter_segments_treats_missing_speaker_as_question_mark():
    payload = {"segments": [
        {"speaker": None, "text": "unknown"},
        {"speaker": "A", "text": "alpha"},
    ]}
    out = _filter_segments(payload, frozenset({"?"}))
    assert [s["text"] for s in out["segments"]] == ["alpha"]


def test_filter_segments_unknown_label_is_noop():
    payload = {"segments": [
        {"speaker": "A", "text": "alpha"},
        {"speaker": "B", "text": "bravo"},
    ]}
    out = _filter_segments(payload, frozenset({"Z"}))
    assert [s["text"] for s in out["segments"]] == ["alpha", "bravo"]


def test_unique_speakers_dedupes_sorts_and_includes_question_mark():
    payload = {"segments": [
        {"speaker": "B"},
        {"speaker": "A"},
        {"speaker": None},
        {"speaker": "A"},
        {"speaker": ""},
    ]}
    assert _unique_speakers(payload) == ["?", "A", "B"]
