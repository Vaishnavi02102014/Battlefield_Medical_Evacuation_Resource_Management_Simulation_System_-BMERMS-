"""
helper.py

Small utility helpers used by the simulation generators.
These functions are intentionally lightweight and contain
only static seed data required for synthetic simulation.
"""

from __future__ import annotations

from typing import Dict, Tuple


# ---------------------------------------------------------------------
# Seed categorical values used when generating synthetic casualties.
# ---------------------------------------------------------------------
from backend.utils.constants import (
    UNITS,
    RANKS,
    BATTLE_SECTORS,
    SECTOR_GRID_ANCHORS,
)

_SEED_CATEGORICALS = {
    "units": UNITS,
    "ranks": RANKS,
    "sectors": BATTLE_SECTORS,
}


def load_seed_categoricals() -> Dict[str, list]:
    """
    Return static seed categorical values used by the
    synthetic casualty generator.
    """
    return _SEED_CATEGORICALS.copy()


# ---------------------------------------------------------------------
# Sector anchor coordinates used by event generation.
# Adjust these coordinates later to match your tactical map.
# ---------------------------------------------------------------------

def get_sector_anchor(sector: str) -> dict:
    return SECTOR_GRID_ANCHORS.get(
        sector,
        {"grid_x": 50.0, "grid_y": 50.0},
    )