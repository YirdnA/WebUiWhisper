from __future__ import annotations

from app.deps import issue_csrf, verify_csrf_token


def test_round_trip(tmp_settings):
    tok = issue_csrf(tmp_settings)
    assert verify_csrf_token(tok, tok, tmp_settings)


def test_mismatched_cookie_and_form(tmp_settings):
    tok1 = issue_csrf(tmp_settings)
    tok2 = issue_csrf(tmp_settings)
    assert tok1 != tok2
    assert not verify_csrf_token(tok1, tok2, tmp_settings)


def test_unsigned_token_rejected(tmp_settings):
    assert not verify_csrf_token("garbage", "garbage", tmp_settings)


def test_missing_token_rejected(tmp_settings):
    assert not verify_csrf_token(None, "x", tmp_settings)
    assert not verify_csrf_token("x", None, tmp_settings)
