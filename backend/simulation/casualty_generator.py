"""
casualty_generator.py

Responsible ONLY for generating casualty attributes for a given incident.
Does not assign facilities, priorities, or beds (see decision_engine.py)
and does not touch the database.
"""

from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timedelta
import random

from backend.simulation.event_generator import IncidentDraft
from backend.utils.constants import SEVERITY_LIST, SEVERITY_WEIGHTS, INJURY_TYPES
from backend.utils.helper import load_seed_categoricals


@dataclass
class CasualtyDraft:
    """A generated casualty, not yet routed, prioritized, or persisted."""
    battle_sector: str
    grid_x: float
    grid_y: float
    soldier_unit: str
    rank: str
    age: int
    injury_type: str
    severity: str
    arrival_time: datetime


def _draw_severities(count: int, rng: random.Random) -> list[str]:
    weights = [SEVERITY_WEIGHTS[s] for s in SEVERITY_LIST]
    return rng.choices(SEVERITY_LIST, weights=weights, k=count)


def generate_casualties(incident: IncidentDraft, rng: random.Random) -> list[CasualtyDraft]:
    """
    Generate `incident.number_of_casualties` casualty drafts for one incident.
    Casualties are scattered slightly around the incident's grid location and
    arrive at staggered times (2-20 simulated minutes after the incident),
    representing the time it takes to discover and reach each casualty.
    """
    severities = _draw_severities(incident.number_of_casualties, rng)
    categoricals = load_seed_categoricals()
    drafts: list[CasualtyDraft] = []

    for severity in severities:
        drafts.append(
            CasualtyDraft(
                battle_sector=incident.battle_sector,
                grid_x=round(incident.grid_x + rng.uniform(-0.8, 0.8), 2),
                grid_y=round(incident.grid_y + rng.uniform(-0.8, 0.8), 2),
                soldier_unit=rng.choice(categoricals["units"]),
                rank=rng.choice(categoricals["ranks"]),
                age=rng.randint(19, 45),
                injury_type=rng.choice(INJURY_TYPES),
                severity=severity,
                arrival_time=incident.incident_time + timedelta(minutes=rng.randint(2, 20)),
            )
        )
    return drafts
