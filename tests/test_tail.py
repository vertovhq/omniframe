"""The tail after the last thing in a plan (task 20.11 follow-up): at most 0.3 s when the length is derived,
and an explicit `duration` (the length the user asked for) is kept exactly."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from argus.plan import TAIL_S, derive_duration, validate_plan  # noqa: E402


def _plan(**extra) -> object:
    data = {"version": 2, "format": "9:16", "style": "dark",
            "scenes": [{"kind": "big", "at": 0, "text": "x"}], **extra}
    plan, errors = validate_plan(data)
    assert plan is not None, errors
    return plan


def test_the_derived_tail_is_at_most_0_3_seconds() -> None:
    assert TAIL_S <= 0.3
    plan = _plan()
    assert derive_duration(plan, voice_duration=14.96) == pytest.approx(14.96 + 0.3, abs=1e-6)


def test_an_explicit_duration_is_the_final_length_even_when_the_voice_is_shorter() -> None:
    plan = _plan(duration=15)
    assert plan.resolved(voice_duration=14.96).duration == 15
