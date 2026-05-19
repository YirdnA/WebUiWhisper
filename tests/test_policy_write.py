"""Policy editor helpers: read, validate, atomic write."""
from __future__ import annotations

import json

import pytest

from app.routes.policy import _read_policy, _validate, _write_policy


def test_read_policy_returns_empty_for_missing_file(tmp_path):
    assert _read_policy(tmp_path / "missing.json") == {}


def test_read_policy_returns_empty_for_bad_json(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text("{not json", encoding="utf-8")
    assert _read_policy(p) == {}


def test_read_policy_returns_empty_for_non_object(tmp_path):
    p = tmp_path / "arr.json"
    p.write_text("[1, 2, 3]", encoding="utf-8")
    assert _read_policy(p) == {}


def test_read_policy_returns_dict(tmp_path):
    p = tmp_path / "good.json"
    p.write_text('{"backup_retention_days": 14}', encoding="utf-8")
    assert _read_policy(p) == {"backup_retention_days": 14}


def test_validate_accepts_clean_form():
    form = {
        "backup_retention_days": "14",
        "max_cpu": "0.5",
        "min_ram_gb": "6.0",
    }
    clean, errors = _validate(form)
    assert errors == {}
    assert clean == {
        "backup_retention_days": 14,
        "max_cpu": 0.5,
        "min_ram_gb": 6.0,
    }


def test_validate_omits_empty_values():
    """An empty field should drop out so the watcher falls back to its env default."""
    form = {"backup_retention_days": "", "max_cpu": "0.8", "min_ram_gb": ""}
    clean, errors = _validate(form)
    assert errors == {}
    assert clean == {"max_cpu": 0.8}


def test_validate_flags_non_numeric():
    form = {"backup_retention_days": "fourteen"}
    clean, errors = _validate(form)
    assert "backup_retention_days" in errors
    assert clean == {}


def test_validate_flags_out_of_range():
    form = {
        "backup_retention_days": "0",       # below lo
        "max_cpu": "100",                   # above hi
        "min_ram_gb": "0",                  # below lo
    }
    clean, errors = _validate(form)
    assert set(errors) == {"backup_retention_days", "max_cpu", "min_ram_gb"}
    assert clean == {}


def test_write_policy_round_trip(tmp_path):
    p = tmp_path / "policy.json"
    _write_policy(p, {"backup_retention_days": 14, "max_cpu": 0.6})
    body = p.read_text(encoding="utf-8")
    parsed = json.loads(body)
    assert parsed == {"backup_retention_days": 14, "max_cpu": 0.6}
    # Tmp file should be gone after atomic rename.
    assert not (tmp_path / "policy.json.tmp").exists()


def test_write_policy_creates_parent_dir(tmp_path):
    target = tmp_path / "newdir" / "policy.json"
    _write_policy(target, {"max_cpu": 0.5})
    assert target.is_file()
    assert json.loads(target.read_text()) == {"max_cpu": 0.5}


def test_write_policy_overwrites_existing(tmp_path):
    p = tmp_path / "policy.json"
    p.write_text('{"backup_retention_days": 6}', encoding="utf-8")
    _write_policy(p, {"backup_retention_days": 30})
    assert json.loads(p.read_text()) == {"backup_retention_days": 30}
