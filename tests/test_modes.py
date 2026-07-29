from __future__ import annotations

import pytest

from radiolink.modes import threshold_dbm


def test_receiver_override_takes_precedence(reference_project) -> None:
    threshold, details = threshold_dbm(
        reference_project.terminal_b.receiver, "FM"
    )
    assert threshold == pytest.approx(-120.98)
    assert details["source"] == "receiver_override"


def test_ssb_threshold_is_derived(reference_project) -> None:
    threshold, details = threshold_dbm(
        reference_project.terminal_b.receiver, "SSB"
    )
    assert threshold == pytest.approx(-128.198, abs=0.01)
    assert details["source"] == "thermal_noise_budget"
