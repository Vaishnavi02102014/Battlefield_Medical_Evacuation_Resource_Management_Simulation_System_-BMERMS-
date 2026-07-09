"""
simulation_clock.py

A purely virtual clock. It has no relationship to wall-clock time — it only
advances when the Streamlit auto-refresh loop calls `advance()`, by an
amount controlled by simulation speed (1x/2x/5x/10x).

This class has zero dependencies on Streamlit, sqlite, or any other layer,
so it can be unit tested in isolation and safely stored in st.session_state.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional


@dataclass
class SimulationClock:
    start_time: datetime
    current_time: datetime = field(default=None)  # type: ignore[assignment]
    speed: int = 1
    is_running: bool = False

    def __post_init__(self) -> None:
        if self.current_time is None:
            self.current_time = self.start_time

    def advance(self, base_minutes: int) -> None:
        """Advance the clock by base_minutes * speed, only while running."""
        if not self.is_running:
            return
        self.current_time += timedelta(minutes=base_minutes * self.speed)

    def start(self) -> None:
        self.is_running = True

    def pause(self) -> None:
        self.is_running = False

    def set_speed(self, speed: int) -> None:
        self.speed = speed

    def reset(self, start_time: Optional[datetime] = None) -> None:
        self.start_time = start_time or self.start_time
        self.current_time = self.start_time
        self.is_running = False

    @property
    def simulation_day(self) -> int:
        """1-indexed simulated day number since start_time."""
        return (self.current_time.date() - self.start_time.date()).days + 1

    def formatted_time(self) -> str:
        """HH:MM for compact display (e.g. Simulation Status panel)."""
        return self.current_time.strftime("%H:%M")

    def formatted_datetime(self) -> str:
        """Canonical string format used for all DB timestamp columns."""
        return self.current_time.strftime("%Y-%m-%d %H:%M")

    @staticmethod
    def parse(timestamp_str: str) -> datetime:
        """Parse a DB timestamp string back into a datetime, matching formatted_datetime()."""
        return datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M")
