"""
mission_log.py

Defines the structured Mission Log entry produced by every simulation
module. This dataclass is deliberately storage-agnostic: per the approved
architecture, the Mission Log itself lives in Streamlit's session_state
(never persisted to the database), but the entry *shape* is defined here so
every producer (decision_engine, treatment_engine, resource_manager,
simulation_controller) builds the same structure consistently.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Optional

# Closed set of categories used across the simulation engine. Keeping this
# closed (rather than free-text) makes the Dashboard's Mission Log filterable
# and consistently styleable per category.
CATEGORY_INCIDENT = "Incident"
CATEGORY_DISPATCH = "Dispatch"
CATEGORY_ADMISSION = "Admission"
CATEGORY_QUEUE = "Queue"
CATEGORY_RECOVERY = "Recovery"
CATEGORY_RETURN_TO_DUTY = "Return To Duty"
CATEGORY_RESOURCE = "Resource"

MISSION_LOG_CATEGORIES: list[str] = [
    CATEGORY_INCIDENT,
    CATEGORY_DISPATCH,
    CATEGORY_ADMISSION,
    CATEGORY_QUEUE,
    CATEGORY_RECOVERY,
    CATEGORY_RETURN_TO_DUTY,
    CATEGORY_RESOURCE,
]


@dataclass
class MissionLogEntry:
    """One structured Mission Log line."""
    timestamp: str                      # simulated clock time, "YYYY-MM-DD HH:MM"
    category: str                       # one of MISSION_LOG_CATEGORIES
    message: str                        # human-readable description
    facility: Optional[str] = None      # facility_code, if relevant (e.g. "RAP")
    severity: Optional[str] = None      # casualty severity, if relevant


def make_entry(
    timestamp: str,
    category: str,
    message: str,
    facility: Optional[str] = None,
    severity: Optional[str] = None,
) -> MissionLogEntry:
    """Small factory to keep call sites concise and consistent."""
    return MissionLogEntry(
        timestamp=timestamp,
        category=category,
        message=message,
        facility=facility,
        severity=severity,
    )
