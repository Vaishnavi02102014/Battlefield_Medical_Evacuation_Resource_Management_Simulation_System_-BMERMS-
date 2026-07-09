"""
treatment_engine.py

Responsible ONLY for treatment timers: detecting when a casualty's
treatment_end has passed on the simulation clock, and driving the
Recovery -> Return To Duty transition plus bed release / queue promotion.

Per the specification's fixed evacuation model, a casualty is treated at
exactly one facility (determined by severity), not a multi-hop chain — so
there is no further facility to transfer to once treatment ends.

Recovery and Return To Duty are modeled as two distinct, separately timed
stages (not collapsed into the same tick):
    1. process_due_treatments(): treatment timer elapses -> status
       "Recovered", bed released, next queued casualty promoted. The
       casualty's return_to_duty field is set to a scheduled future
       timestamp (current time + RETURN_TO_DUTY_OUTPROCESSING_MINUTES),
       representing administrative outprocessing time.
    2. process_due_return_to_duty(): once that scheduled time elapses,
       status finalizes to "Returned To Duty".
This keeps "Recovered" a real, observable dashboard count rather than an
instantaneous pass-through state.
"""

from __future__ import annotations
from dataclasses import dataclass
from datetime import timedelta

from backend.database import crud
from backend.simulation.simulation_clock import SimulationClock
from backend.simulation import bed_manager
from backend.simulation.mission_log import MissionLogEntry, make_entry, CATEGORY_RECOVERY, CATEGORY_RETURN_TO_DUTY, CATEGORY_ADMISSION, CATEGORY_QUEUE
from backend.utils.config import RETURN_TO_DUTY_OUTPROCESSING_MINUTES


@dataclass
class TreatmentCompletionEvent:
    casualty_id: str
    facility_code: str
    freed_bed_promoted_casualty: str | None
    log_entries: list[MissionLogEntry]


def process_due_treatments(clock: SimulationClock) -> list[TreatmentCompletionEvent]:
    """
    Find every treatment whose end time has passed, complete it, mark the
    casualty Recovered (with a scheduled Return To Duty time), release
    their bed, and promote the next waiting casualty (if any) into the
    freed bed.
    """
    events: list[TreatmentCompletionEvent] = []
    due_treatments = crud.get_due_treatments(clock.formatted_datetime())

    for treatment in due_treatments:
        casualty = crud.get_casualty(treatment.casualty_id)
        facility = crud.get_facility_by_id(treatment.facility_id)
        if casualty is None or facility is None:
            continue

        crud.complete_treatment(treatment.treatment_id)

        scheduled_rtd = clock.current_time + timedelta(minutes=RETURN_TO_DUTY_OUTPROCESSING_MINUTES)
        crud.update_casualty_status(
            casualty.casualty_id, "Recovered", return_to_duty=scheduled_rtd.strftime("%Y-%m-%d %H:%M")
        )

        entries = [
            make_entry(
                timestamp=clock.formatted_datetime(),
                category=CATEGORY_RECOVERY,
                message=f"{casualty.casualty_id} recovered at {facility.facility_code}",
                facility=facility.facility_code,
                severity=casualty.severity,
            )
        ]

        promoted = None
        if casualty.bed_id is not None:
            promotion = bed_manager.release_bed_and_promote(casualty.bed_id, treatment.facility_id, clock)
            if promotion is not None:
                promoted = promotion["casualty_id"]
                promoted_category = CATEGORY_ADMISSION if promotion["status"] == "Under Treatment" else CATEGORY_QUEUE
                entries.append(
                    make_entry(
                        timestamp=clock.formatted_datetime(),
                        category=promoted_category,
                        message=(
                            f"Bed released at {facility.facility_code}; "
                            f"{promoted} admitted from waiting queue ({promotion['status']})"
                        ),
                        facility=facility.facility_code,
                    )
                )
            else:
                entries.append(
                    make_entry(
                        timestamp=clock.formatted_datetime(),
                        category=CATEGORY_RECOVERY,
                        message=f"Bed released at {facility.facility_code}",
                        facility=facility.facility_code,
                    )
                )

        events.append(
            TreatmentCompletionEvent(
                casualty_id=casualty.casualty_id,
                facility_code=facility.facility_code,
                freed_bed_promoted_casualty=promoted,
                log_entries=entries,
            )
        )

    return events


def process_due_return_to_duty(clock: SimulationClock) -> list[MissionLogEntry]:
    """
    Finalize any 'Recovered' casualty whose outprocessing delay has elapsed
    to 'Returned To Duty'. Called every tick by simulation_controller.
    """
    entries: list[MissionLogEntry] = []
    for casualty in crud.get_due_return_to_duty(clock.formatted_datetime()):
        crud.update_casualty_status(casualty.casualty_id, "Returned To Duty", return_to_duty=casualty.return_to_duty)
        entries.append(
            make_entry(
                timestamp=clock.formatted_datetime(),
                category=CATEGORY_RETURN_TO_DUTY,
                message=f"{casualty.casualty_id} returned to duty",
                severity=casualty.severity,
            )
        )
    return entries
