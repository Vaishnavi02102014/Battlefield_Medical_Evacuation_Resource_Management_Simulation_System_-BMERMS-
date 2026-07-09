"""
event_generator.py

Responsible ONLY for deciding *when* a battlefield incident happens and
*what* it looks like at a high level (type, sector, casualty count).
It does NOT generate individual casualties (see casualty_generator.py) and
it does NOT touch the database — simulation_controller.py persists whatever
this module produces.

Incidents are paced (utils/config.MIN/MAX_MINUTES_BETWEEN_INCIDENTS) so the
simulation "feels" like discrete battlefield events rather than a constant
random drip of casualties, per the specification's simulation philosophy.
"""

from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
import random

from backend.utils.constants import INCIDENT_TYPES, INCIDENT_SIZE_BUCKETS
from backend.utils.config import MIN_MINUTES_BETWEEN_INCIDENTS, MAX_MINUTES_BETWEEN_INCIDENTS
from backend.utils.helper import load_seed_categoricals, get_sector_anchor


@dataclass
class IncidentDraft:
    """An incident that has been decided but not yet persisted."""
    event_type: str
    battle_sector: str
    grid_x: float
    grid_y: float
    number_of_casualties: int
    incident_time: datetime


class EventGenerator:
    """
    Stateful pacing engine: tracks simulated minutes since the last incident
    and fires a new one once a randomly-chosen interval has elapsed.
    """

    def __init__(self, rng: random.Random) -> None:
        self.rng = rng
        self.minutes_since_last_incident: int = 0
        self.next_incident_due_in_minutes: int = self._roll_next_interval()

    def _roll_next_interval(self) -> int:
        return self.rng.randint(MIN_MINUTES_BETWEEN_INCIDENTS, MAX_MINUTES_BETWEEN_INCIDENTS)

    def _random_location(self) -> tuple[str, float, float]:
        sectors = load_seed_categoricals()["sectors"]
        sector = self.rng.choice(sectors)
        anchor = get_sector_anchor(sector)
        grid_x = round(anchor["grid_x"] + self.rng.uniform(-4.0, 4.0), 2)
        grid_y = round(anchor["grid_y"] + self.rng.uniform(-1.5, 1.5), 2)
        return sector, grid_x, grid_y

    def _draw_casualty_count(self) -> int:
        """
        Weighted incident size: mostly Small, occasionally Medium, rarely a
        Mass Casualty event — rather than a flat uniform 2-25 draw.
        """
        bucket_names = list(INCIDENT_SIZE_BUCKETS.keys())
        weights = [INCIDENT_SIZE_BUCKETS[name]["weight"] for name in bucket_names]
        chosen_bucket = self.rng.choices(bucket_names, weights=weights, k=1)[0]
        low, high = INCIDENT_SIZE_BUCKETS[chosen_bucket]["range"]
        return self.rng.randint(low, high)

    def tick(self, elapsed_minutes: int, current_time: datetime) -> IncidentDraft | None:
        """
        Advance the internal pacing counter by elapsed_minutes. Returns an
        IncidentDraft if an incident should fire this tick, else None.
        """
        self.minutes_since_last_incident += elapsed_minutes
        if self.minutes_since_last_incident < self.next_incident_due_in_minutes:
            return None

        self.minutes_since_last_incident = 0
        self.next_incident_due_in_minutes = self._roll_next_interval()

        event_type = self.rng.choice(INCIDENT_TYPES)
        sector, grid_x, grid_y = self._random_location()
        casualty_count = self._draw_casualty_count()

        return IncidentDraft(
            event_type=event_type,
            battle_sector=sector,
            grid_x=grid_x,
            grid_y=grid_y,
            number_of_casualties=casualty_count,
            incident_time=current_time,
        )

    def force_incident(
        self,
        event_type: str,
        current_time: datetime,
        casualty_count: int | None = None,
    ) -> IncidentDraft:
        """
        Immediately produce an incident of a specific type, bypassing pacing.
        Used by the Simulation page's manual "Generate X" buttons.
        Resets the pacing counter so a manual event doesn't get immediately
        followed by an automatic one.
        """
        sector, grid_x, grid_y = self._random_location()
        count = casualty_count if casualty_count is not None else self._draw_casualty_count()
        self.minutes_since_last_incident = 0
        self.next_incident_due_in_minutes = self._roll_next_interval()

        return IncidentDraft(
            event_type=event_type,
            battle_sector=sector,
            grid_x=grid_x,
            grid_y=grid_y,
            number_of_casualties=count,
            incident_time=current_time,
        )
