"""
config.py

Runtime-configurable parameters — things a user could reasonably change via
the Settings page or an environment variable without altering any business
rule. This is intentionally kept separate from utils/constants.py, which
holds FIXED domain rules (facility capacities, severity mapping, etc.) that
must never change at runtime.

Nothing in this file should be treated as immutable: the Settings page is
expected to read/write session-state copies seeded from these defaults.
"""

from __future__ import annotations

# --------------------------------------------------------------------------
# SIMULATION CLOCK
# --------------------------------------------------------------------------
SIMULATION_SPEEDS: list[int] = [1, 2, 5, 10]
DEFAULT_SIMULATION_SPEED: int = 1

# Simulated minutes advanced per auto-refresh tick, before the speed
# multiplier is applied. E.g. at speed=5 and this=1, each rerun advances
# the simulated clock by 5 simulated minutes.
SIMULATED_MINUTES_PER_TICK: int = 1

# --------------------------------------------------------------------------
# AUTO-REFRESH (drives the simulation clock; no background threads)
# --------------------------------------------------------------------------
DEFAULT_AUTOREFRESH_INTERVAL_MS: int = 3000
MIN_AUTOREFRESH_INTERVAL_MS: int = 1000
MAX_AUTOREFRESH_INTERVAL_MS: int = 10000

# --------------------------------------------------------------------------
# MISSION LOG (in-memory, session_state only — never persisted to DB)
# --------------------------------------------------------------------------
DEFAULT_MISSION_LOG_MAX_ENTRIES: int = 200

# --------------------------------------------------------------------------
# RANDOMNESS
# Setting a fixed seed makes a simulation run reproducible for testing/demo
# purposes. None = fully random each run.
# --------------------------------------------------------------------------
DEFAULT_RANDOM_SEED: int | None = None

# --------------------------------------------------------------------------
# UI / UX TOGGLES (Settings page)
# --------------------------------------------------------------------------
DEFAULT_ANIMATIONS_ENABLED: bool = True
DEFAULT_ALERT_SOUND_ENABLED: bool = False
DEFAULT_SHOW_GRID: bool = True

# --------------------------------------------------------------------------
# INCIDENT PACING
# Minimum/maximum simulated minutes between two consecutive battlefield
# incidents, so events feel deliberate rather than constant.
# --------------------------------------------------------------------------
MIN_MINUTES_BETWEEN_INCIDENTS: int = 15
MAX_MINUTES_BETWEEN_INCIDENTS: int = 90

# Administrative processing time after recovery before a soldier is
# considered Returned To Duty.
RETURN_TO_DUTY_OUTPROCESSING_MINUTES: int = 30