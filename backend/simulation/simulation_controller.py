"""
simulation_controller.py

The ONLY module that coordinates the full simulation hierarchy end to end:

    Scenario -> Operation -> Incident -> Casualty -> Decision Engine
    -> Treatment -> Recovery -> Return To Duty

This module has ZERO Streamlit dependency. It is a plain Python class that
a caller (a Streamlit page, a script, or a test) drives by calling
run_tick() repeatedly. All randomness flows through a single
random.Random instance seeded once at construction, so an entire run is
fully reproducible when a seed is supplied (utils.config.DEFAULT_RANDOM_SEED
or an explicit seed passed in).

Per-tick order of operations (chosen deliberately):
    1. Advance the clock.
    2. Release transport resources whose transit/return time has elapsed.
    3. Admit casualties whose evacuation transit has completed.
    4. Complete treatments whose timer has elapsed (recovery + bed release
       + promotion of the next queued casualty).
    5. Refresh queue waiting times.
    6. Possibly generate a new battlefield incident (and its casualties).
    7. Evaluate medical-team surge dispatch/release per facility.
"""

from __future__ import annotations
import random
from typing import Optional

from backend.database import crud
from backend.simulation.simulation_clock import SimulationClock
from backend.simulation.event_generator import EventGenerator, IncidentDraft
from backend.simulation import casualty_generator, decision_engine, treatment_engine, queue_manager, resource_manager
from backend.simulation.mission_log import MissionLogEntry, make_entry, CATEGORY_INCIDENT
from backend.utils.config import SIMULATED_MINUTES_PER_TICK, DEFAULT_RANDOM_SEED

DEFAULT_SCENARIO_NAME = "Operation Iron Shield"
DEFAULT_OPERATION_NAME = "Sector Sweep Alpha"


class SimulationController:
    def __init__(self, clock: SimulationClock, seed: Optional[int] = DEFAULT_RANDOM_SEED) -> None:
        self.clock = clock
        self.rng = random.Random(seed)
        self.event_generator = EventGenerator(self.rng)
        self.scenario_id, self.operation_id = self._ensure_scenario_and_operation()

    def _ensure_scenario_and_operation(self) -> tuple[int, int]:
        """Reuse an active Scenario/Operation if one exists, else create the defaults."""
        scenario = crud.get_active_scenario()
        scenario_id = scenario.scenario_id if scenario else crud.create_scenario(
            DEFAULT_SCENARIO_NAME, self.clock.formatted_datetime()
        )

        operation = crud.get_active_operation()
        operation_id = operation.operation_id if operation else crud.create_operation(
            scenario_id, DEFAULT_OPERATION_NAME, self.clock.formatted_datetime()
        )
        return scenario_id, operation_id

    def run_tick(self) -> list[MissionLogEntry]:
        """
        Advance the simulation by one tick. Returns structured Mission Log
        entries for anything noteworthy that happened this tick (empty list
        if the simulation is paused or nothing happened).
        """
        if not self.clock.is_running:
            return []

        self.clock.advance(SIMULATED_MINUTES_PER_TICK)
        elapsed_minutes = SIMULATED_MINUTES_PER_TICK * self.clock.speed

        log_entries: list[MissionLogEntry] = []

        resource_manager.release_due_transport(self.clock)

        log_entries.extend(decision_engine.process_arrived_evacuations(self.clock))

        for completion in treatment_engine.process_due_treatments(self.clock):
            log_entries.extend(completion.log_entries)

        log_entries.extend(treatment_engine.process_due_return_to_duty(self.clock))

        queue_manager.update_waiting_times(self.clock)

        incident_draft = self.event_generator.tick(elapsed_minutes, self.clock.current_time)
        if incident_draft is not None:
            log_entries.extend(self._process_incident(incident_draft))

        for facility in crud.get_all_facilities():
            surge_entry = resource_manager.manage_medical_team_surge(facility.facility_id, facility.queue_length, self.clock)
            if surge_entry:
                log_entries.append(surge_entry)

        return log_entries

    def _process_incident(self, incident_draft: IncidentDraft) -> list[MissionLogEntry]:
        """Persist an incident and generate + route all of its casualties."""
        incident_id = crud.get_next_incident_id()
        crud.insert_incident(
            incident_id=incident_id,
            operation_id=self.operation_id,
            incident_time=self.clock.formatted_datetime(),
            event_type=incident_draft.event_type,
            battle_sector=incident_draft.battle_sector,
            grid_x=incident_draft.grid_x,
            grid_y=incident_draft.grid_y,
            number_of_casualties=incident_draft.number_of_casualties,
        )

        entries: list[MissionLogEntry] = [
            make_entry(
                timestamp=self.clock.formatted_datetime(),
                category=CATEGORY_INCIDENT,
                message=(
                    f"{incident_draft.event_type} reported in Sector {incident_draft.battle_sector} "
                    f"— {incident_draft.number_of_casualties} casualties"
                ),
            )
        ]

        casualty_drafts = casualty_generator.generate_casualties(incident_draft, self.rng)
        for draft in casualty_drafts:
            result = decision_engine.process_casualty(draft, incident_id, self.clock, self.rng)
            entries.append(result.log_entry)

        return entries

    def trigger_manual_incident(self, event_type: str, casualty_count: Optional[int] = None) -> list[MissionLogEntry]:
        """
        Immediately fire a specific incident type, bypassing normal pacing.
        Used by the Simulation page's "Generate Mortar Attack" etc. buttons.
        """
        draft = self.event_generator.force_incident(event_type, self.clock.current_time, casualty_count)
        return self._process_incident(draft)
