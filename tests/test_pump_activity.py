"""Pump activity from the runtime counter, not from runStatus (W4/W5/CTW2).

Measured on a W4XUVC (Eversweet 3 Pro UVC, firmware 63) on 2026-10-19: in a 3 min on / 3 min off cycle
CMD 210's ``runStatus`` (byte 11) stayed 1 the whole time, while ``pumpRunTime`` (bytes 6-9, seconds)
advanced only while the pump turned -- +12, +0, +3, +64, +64 s over consecutive ~65 s polls. So
"pump running" (and the power/energy sensors built on it) read "on" around the clock, and an alert on
"pump off for 10 min" could never fire.
"""

from __future__ import annotations

from custom_components.petkit_ble.ble_client import PetkitFountainData
from custom_components.petkit_ble.const import ALIAS_CTW3, ALIAS_W4XUVC, POLL_INTERVAL
from custom_components.petkit_ble.coordinator import (
    PUMP_ACTIVITY_MAX_GAP_S,
    _apply_pump_activity,
    _pump_active_from_runtime,
)

# (seconds since the first poll, pumpRunTime) as read on 2026-10-19 11:41:05..11:46:28 local time.
MEASURED = [(0, 0x080EA1), (65, 0x080EAD), (130, 0x080EAD), (194, 0x080EB0), (258, 0x080EF0), (323, 0x080F30)]


def _w4(runtime: int, running_status: int = 1) -> PetkitFountainData:
    return PetkitFountainData(
        alias=ALIAS_W4XUVC, power_status=1, mode=1, running_status=running_status, pump_runtime=runtime
    )


def test_the_measured_cycle_reads_on_off_on_on_on() -> None:
    prev = None
    seen = []
    for t, runtime in MEASURED:
        data = _w4(runtime)  # runStatus stuck at 1, as measured
        prev = _apply_pump_activity(data, prev, float(t))
        seen.append(data.is_pump_running)
    # The first poll has nothing to compare with, so it falls back to runStatus.
    assert seen == [True, True, False, True, True, True]


def test_a_counter_that_did_not_move_means_off_even_if_run_status_says_on() -> None:
    assert _pump_active_from_runtime((1000, 0.0), 1000, 65.0) is False
    data = _w4(1000)
    data.pump_active = False
    assert data.is_pump_running is False
    assert data.power_w == 0.0, "power follows the real pump state (energy comes from the daily counter anyway)"


def test_unknown_falls_back_to_run_status() -> None:
    assert _pump_active_from_runtime(None, 1000, 0.0) is None, "first poll"
    assert _pump_active_from_runtime((5000, 0.0), 1000, 65.0) is None, "counter reset (it did: 7.27 M -> 0.53 M s)"
    assert _pump_active_from_runtime((1000, 0.0), 1064, PUMP_ACTIVITY_MAX_GAP_S + 1) is None, (
        "after a long gap a delta says the pump ran SOMETIME, not that it runs now"
    )
    assert _w4(1000, running_status=1).is_pump_running is True
    assert _w4(1000, running_status=0).is_pump_running is False


def test_the_gap_limit_tolerates_one_missed_poll() -> None:
    assert PUMP_ACTIVITY_MAX_GAP_S > 2 * POLL_INTERVAL
    assert _pump_active_from_runtime((1000, 0.0), 1001, 2 * POLL_INTERVAL + 10) is True


def test_ctw3_keeps_its_own_run_status() -> None:
    """Not measured on a CTW3, whose bytes 9..18 tick every poll (issue #65): leave it alone."""
    data = PetkitFountainData(alias=ALIAS_CTW3, power_status=1, mode=1, running_status=1, pump_runtime=2000)
    prev = _apply_pump_activity(data, (2000, 0.0), 65.0)
    assert data.pump_active is None
    assert data.is_pump_running is True
    assert prev == (2000, 65.0)
