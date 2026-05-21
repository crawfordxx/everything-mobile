"""SessionGovernor: per-account daily caps + persistence."""

from __future__ import annotations

from pathlib import Path

import pytest

from mobilecli.envelope import EmError, ErrorCode
from mobilecli.safety.governor import SessionGovernor


@pytest.fixture
def tmp_state(tmp_path) -> Path:
    return tmp_path / "session.json"


def test_governor_allows_first_action(tmp_state):
    g = SessionGovernor(state_path=tmp_state, account="t", caps={"comment": 20})
    g.check_or_raise("comment")  # no exception


def test_governor_persists_after_record(tmp_state):
    g = SessionGovernor(state_path=tmp_state, account="t", caps={"comment": 20})
    g.record("comment")
    g2 = SessionGovernor(state_path=tmp_state, account="t", caps={"comment": 20})
    assert g2._counts_today()["comment"] == 1


def test_governor_raises_rate_limited_at_cap(tmp_state):
    g = SessionGovernor(state_path=tmp_state, account="t", caps={"comment": 2})
    g.record("comment")
    g.record("comment")
    with pytest.raises(EmError) as exc:
        g.check_or_raise("comment")
    assert exc.value.code is ErrorCode.RATE_LIMITED


def test_governor_separate_accounts_isolated(tmp_path):
    state_a = tmp_path / "a.json"
    state_b = tmp_path / "b.json"
    g_a = SessionGovernor(state_path=state_a, account="a", caps={"comment": 1})
    g_a.record("comment")
    g_b = SessionGovernor(state_path=state_b, account="b", caps={"comment": 1})
    g_b.check_or_raise("comment")  # b unaffected


def test_governor_no_cap_means_no_limit(tmp_state):
    g = SessionGovernor(state_path=tmp_state, account="t", caps={})
    for _ in range(100):
        g.check_or_raise("uncapped")
        g.record("uncapped")
