
"""
init_db.py
 
Creates the database schema (10 tables) and seeds static/reference data:
    - the four fixed treatment facilities and their beds
    - the fixed resource fleets (ambulances, helicopters, medical teams)
 
This module is idempotent: running it multiple times will not duplicate
facilities, beds, or fleet resources.
 
Transport architecture note (schema alignment): Casualties.evacuation_mode
and Casualties.evacuation_arrival_time are both nullable. A casualty that
is placed in the runtime transport queue (no vehicle available at triage
time - see resource_manager.dispatch_transport / decision_engine) is
persisted with status="Awaiting Transport", evacuation_mode=NULL, and
evacuation_arrival_time=NULL - there is no vehicle and no ETA yet, and no
placeholder string ("Queued", "Unknown", etc.) is ever substituted for
NULL. A freshly created database already has evacuation_mode as a nullable
column (see the Casualties CREATE TABLE statement below). An existing
database created before this change had evacuation_mode as NOT NULL;
create_schema() detects and migrates that case automatically - see
_casualties_needs_evacuation_mode_migration() /
_migrate_casualties_evacuation_mode_nullable() below.
 
Run standalone with:
    python -m database.init_db
"""
 
from __future__ import annotations
import logging
 
from backend.database.db import get_connection
from backend.utils.constants import (
    FACILITY_CONFIG,
    FACILITY_ORDER,
    AMBULANCE_FLEET_SIZE,
    HELICOPTER_FLEET_SIZE,
    MEDICAL_TEAM_COUNT,
    MEDICAL_TEAM_ROLES,
    FACILITY_STATUS_OPERATIONAL,
    DATABASE_PATH,
    VEHICLE_INITIAL_POSITIONS,
)
 
logger = logging.getLogger(__name__)
 
# --------------------------------------------------------------------------
# SCHEMA
# --------------------------------------------------------------------------
SCHEMA_STATEMENTS: list[str] = [
    # 1. FACILITIES
    """
    CREATE TABLE IF NOT EXISTS Facilities (
        facility_id INTEGER PRIMARY KEY AUTOINCREMENT,
        facility_name TEXT NOT NULL,
        facility_code TEXT NOT NULL UNIQUE,
        capacity INTEGER NOT NULL,
        occupied_beds INTEGER NOT NULL DEFAULT 0,
        available_beds INTEGER NOT NULL,
        queue_length INTEGER NOT NULL DEFAULT 0,
        treatment_duration_hours REAL NOT NULL,
        facility_status TEXT NOT NULL DEFAULT 'Operational',
        grid_x REAL NOT NULL,
        grid_y REAL NOT NULL
    );
    """,
    # 2. BEDS
    """
    CREATE TABLE IF NOT EXISTS Beds (
        bed_id INTEGER PRIMARY KEY AUTOINCREMENT,
        facility_id INTEGER NOT NULL,
        bed_number INTEGER NOT NULL,
        status TEXT NOT NULL DEFAULT 'Available',
        current_casualty TEXT,
        occupied_since TEXT,
        expected_release_time TEXT,
        FOREIGN KEY (facility_id) REFERENCES Facilities(facility_id),
        UNIQUE (facility_id, bed_number)
    );
    """,
    # 3. SCENARIOS (top of hierarchy)
    """
    CREATE TABLE IF NOT EXISTS Scenarios (
        scenario_id INTEGER PRIMARY KEY AUTOINCREMENT,
        scenario_name TEXT NOT NULL,
        start_time TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'Active',
        description TEXT
    );
    """,
    # 4. OPERATIONS
    """
    CREATE TABLE IF NOT EXISTS Operations (
        operation_id INTEGER PRIMARY KEY AUTOINCREMENT,
        scenario_id INTEGER NOT NULL,
        operation_name TEXT NOT NULL,
        start_time TEXT NOT NULL,
        end_time TEXT,
        status TEXT NOT NULL DEFAULT 'Active',
        description TEXT,
        FOREIGN KEY (scenario_id) REFERENCES Scenarios(scenario_id)
    );
    """,
    # 5. INCIDENTS
    """
    CREATE TABLE IF NOT EXISTS Incidents (
        incident_id TEXT PRIMARY KEY,
        operation_id INTEGER NOT NULL,
        incident_time TEXT NOT NULL,
        event_type TEXT NOT NULL,
        battle_sector TEXT NOT NULL,
        grid_x REAL NOT NULL,
        grid_y REAL NOT NULL,
        number_of_casualties INTEGER NOT NULL,
        status TEXT NOT NULL DEFAULT 'Active',
        FOREIGN KEY (operation_id) REFERENCES Operations(operation_id)
    );
    """,
    # 6. CASUALTIES
    """
    CREATE TABLE IF NOT EXISTS Casualties (
        casualty_id TEXT PRIMARY KEY,
        incident_id TEXT NOT NULL,
        battle_sector TEXT NOT NULL,
        grid_x REAL NOT NULL,
        grid_y REAL NOT NULL,
        soldier_unit TEXT NOT NULL,
        rank TEXT NOT NULL,
        age INTEGER NOT NULL,
        injury_type TEXT NOT NULL,
        severity TEXT NOT NULL,
        priority TEXT NOT NULL,
        arrival_time TEXT NOT NULL,
        assigned_facility INTEGER,
        bed_id INTEGER,
        queue_position INTEGER,
        evacuation_mode TEXT,
        evacuation_arrival_time TEXT,
        medical_officer TEXT,
        status TEXT NOT NULL DEFAULT 'Waiting',
        expected_recovery TEXT,
        return_to_duty TEXT,
        FOREIGN KEY (incident_id) REFERENCES Incidents(incident_id),
        FOREIGN KEY (assigned_facility) REFERENCES Facilities(facility_id),
        FOREIGN KEY (bed_id) REFERENCES Beds(bed_id)
    );
    """,
    # 7. TREATMENTS
    """
    CREATE TABLE IF NOT EXISTS Treatments (
        treatment_id INTEGER PRIMARY KEY AUTOINCREMENT,
        casualty_id TEXT NOT NULL,
        facility_id INTEGER NOT NULL,
        treatment_start TEXT NOT NULL,
        treatment_end TEXT,
        treatment_duration REAL NOT NULL,
        current_status TEXT NOT NULL DEFAULT 'Under Treatment',
        FOREIGN KEY (casualty_id) REFERENCES Casualties(casualty_id),
        FOREIGN KEY (facility_id) REFERENCES Facilities(facility_id)
    );
    """,
    # 8. WAITING_QUEUE
    """
    CREATE TABLE IF NOT EXISTS Waiting_Queue (
        queue_id INTEGER PRIMARY KEY AUTOINCREMENT,
        facility_id INTEGER NOT NULL,
        casualty_id TEXT NOT NULL,
        priority TEXT NOT NULL,
        arrival_time TEXT NOT NULL,
        waiting_time REAL DEFAULT 0,
        FOREIGN KEY (facility_id) REFERENCES Facilities(facility_id),
        FOREIGN KEY (casualty_id) REFERENCES Casualties(casualty_id)
    );
    """,
    # 9. AMBULANCES
    """
    CREATE TABLE IF NOT EXISTS Ambulances (
        ambulance_id INTEGER PRIMARY KEY AUTOINCREMENT,
        call_sign TEXT NOT NULL UNIQUE,
        status TEXT NOT NULL DEFAULT 'Available',
        assigned_casualty TEXT,
        release_time TEXT,
        grid_x REAL,
        grid_y REAL,
        dispatch_time TEXT,
        origin_grid_x REAL,
        origin_grid_y REAL,
        FOREIGN KEY (assigned_casualty) REFERENCES Casualties(casualty_id)
    );
    """,
    # 10. HELICOPTERS
    """
    CREATE TABLE IF NOT EXISTS Helicopters (
        helicopter_id INTEGER PRIMARY KEY AUTOINCREMENT,
        call_sign TEXT NOT NULL UNIQUE,
        status TEXT NOT NULL DEFAULT 'Available',
        assigned_casualty TEXT,
        release_time TEXT,
        grid_x REAL,
        grid_y REAL,
        dispatch_time TEXT,
        origin_grid_x REAL,
        origin_grid_y REAL,
        FOREIGN KEY (assigned_casualty) REFERENCES Casualties(casualty_id)
    );
    """,
    # 11. MEDICAL_TEAMS
    """
    CREATE TABLE IF NOT EXISTS Medical_Teams (
        team_id INTEGER PRIMARY KEY AUTOINCREMENT,
        team_name TEXT NOT NULL UNIQUE,
        status TEXT NOT NULL DEFAULT 'Available',
        assigned_facility INTEGER,
        specialization TEXT NOT NULL,
        FOREIGN KEY (assigned_facility) REFERENCES Facilities(facility_id)
    );
    """,
]
 
# Helpful indexes for the query patterns the dashboard will hit repeatedly.
INDEX_STATEMENTS: list[str] = [
    "CREATE INDEX IF NOT EXISTS idx_casualties_status ON Casualties(status);",
    "CREATE INDEX IF NOT EXISTS idx_casualties_facility ON Casualties(assigned_facility);",
    "CREATE INDEX IF NOT EXISTS idx_casualties_incident ON Casualties(incident_id);",
    "CREATE INDEX IF NOT EXISTS idx_beds_facility ON Beds(facility_id);",
    "CREATE INDEX IF NOT EXISTS idx_queue_facility ON Waiting_Queue(facility_id);",
    "CREATE INDEX IF NOT EXISTS idx_treatments_casualty ON Treatments(casualty_id);",
    "CREATE INDEX IF NOT EXISTS idx_incidents_operation ON Incidents(operation_id);",
]
 
 
def _casualties_needs_evacuation_mode_migration(conn) -> bool:
    """
    True if a Casualties table already exists AND its evacuation_mode
    column is still NOT NULL (i.e. this DB predates the transport-queue
    architecture, where a queued casualty has no vehicle/mode yet).
 
    Returns False if the Casualties table doesn't exist at all - in that
    case the CREATE TABLE IF NOT EXISTS statement below already defines
    evacuation_mode as nullable, so a fresh database needs no migration.
    """
    columns = conn.execute("PRAGMA table_info(Casualties);").fetchall()
    if not columns:
        return False
    for column in columns:
        if column["name"] == "evacuation_mode" and column["notnull"] == 1:
            return True
    return False
 
 
def _migrate_casualties_evacuation_mode_nullable(conn) -> None:
    """
    Recreate the Casualties table with evacuation_mode (and
    evacuation_arrival_time) as nullable columns, preserving every existing
    row exactly as-is - no column is backfilled with a placeholder value.
 
    SQLite has no ALTER TABLE ... ALTER COLUMN, so removing a NOT NULL
    constraint requires the standard SQLite migration procedure: create a
    new table with the corrected schema, copy all rows across as-is, drop
    the old table, then rename the new one into place. Dropping the old
    Casualties table also drops any indexes defined on it
    (idx_casualties_status, idx_casualties_facility,
    idx_casualties_incident) - those are recreated afterward by
    create_schema()'s normal INDEX_STATEMENTS pass, which runs
    unconditionally right after this function returns.
    """
    conn.execute("PRAGMA foreign_keys = OFF;")
 
    conn.execute(
        """
        CREATE TABLE Casualties_new (
            casualty_id TEXT PRIMARY KEY,
            incident_id TEXT NOT NULL,
            battle_sector TEXT NOT NULL,
            grid_x REAL NOT NULL,
            grid_y REAL NOT NULL,
            soldier_unit TEXT NOT NULL,
            rank TEXT NOT NULL,
            age INTEGER NOT NULL,
            injury_type TEXT NOT NULL,
            severity TEXT NOT NULL,
            priority TEXT NOT NULL,
            arrival_time TEXT NOT NULL,
            assigned_facility INTEGER,
            bed_id INTEGER,
            queue_position INTEGER,
            evacuation_mode TEXT,
            evacuation_arrival_time TEXT,
            medical_officer TEXT,
            status TEXT NOT NULL DEFAULT 'Waiting',
            expected_recovery TEXT,
            return_to_duty TEXT,
            FOREIGN KEY (incident_id) REFERENCES Incidents(incident_id),
            FOREIGN KEY (assigned_facility) REFERENCES Facilities(facility_id),
            FOREIGN KEY (bed_id) REFERENCES Beds(bed_id)
        );
        """
    )
 
    conn.execute(
        """
        INSERT INTO Casualties_new (
            casualty_id, incident_id, battle_sector, grid_x, grid_y,
            soldier_unit, rank, age, injury_type, severity, priority,
            arrival_time, assigned_facility, bed_id, queue_position,
            evacuation_mode, evacuation_arrival_time, medical_officer,
            status, expected_recovery, return_to_duty
        )
        SELECT
            casualty_id, incident_id, battle_sector, grid_x, grid_y,
            soldier_unit, rank, age, injury_type, severity, priority,
            arrival_time, assigned_facility, bed_id, queue_position,
            evacuation_mode, evacuation_arrival_time, medical_officer,
            status, expected_recovery, return_to_duty
        FROM Casualties;
        """
    )
 
    conn.execute("DROP TABLE Casualties;")
    conn.execute("ALTER TABLE Casualties_new RENAME TO Casualties;")
    conn.execute("PRAGMA foreign_keys = ON;")
 
    logger.info(
        "Migrated Casualties.evacuation_mode / evacuation_arrival_time to "
        "nullable columns; all existing rows preserved unchanged."
    )
 
 
# --------------------------------------------------------------------------
# Phase 6A - resource movement metadata migration
#
# Adds three new nullable columns to Ambulances and Helicopters:
# dispatch_time, origin_grid_x, origin_grid_y. Unlike the evacuation_mode
# migration above (which had to remove a NOT NULL constraint and therefore
# required the full create-copy-drop-rename table recreation), this only
# ADDS new nullable columns with no default - SQLite supports
# ALTER TABLE ... ADD COLUMN directly for that case, so no table
# recreation is needed here. Existing rows simply get NULL in the three
# new columns, which is the correct "not yet known" representation - not
# a placeholder value.
# --------------------------------------------------------------------------
_RESOURCE_MOVEMENT_METADATA_COLUMNS: dict[str, str] = {
    "dispatch_time": "TEXT",
    "origin_grid_x": "REAL",
    "origin_grid_y": "REAL",
}
 
 
def _missing_resource_movement_metadata_columns(conn, table_name: str) -> list[tuple[str, str]]:
    """Which of dispatch_time/origin_grid_x/origin_grid_y are missing from `table_name`, if any."""
    existing_columns = {
        row["name"] for row in conn.execute(f"PRAGMA table_info({table_name});").fetchall()
    }
    return [
        (column_name, sql_type)
        for column_name, sql_type in _RESOURCE_MOVEMENT_METADATA_COLUMNS.items()
        if column_name not in existing_columns
    ]
 
 
def _migrate_resource_movement_metadata(conn) -> None:
    """
    Add any missing movement-metadata columns to Ambulances and
    Helicopters. Safe to call every startup - only ALTERs a table when a
    column is actually missing, so a fresh database (already created with
    these columns via SCHEMA_STATEMENTS) is a no-op here.
    """
    for table_name in ("Ambulances", "Helicopters"):
        missing = _missing_resource_movement_metadata_columns(conn, table_name)
        for column_name, sql_type in missing:
            conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {sql_type};")
        if missing:
            logger.info(
                "Added movement-metadata column(s) %s to %s.",
                [column_name for column_name, _ in missing],
                table_name,
            )
 
 
def create_schema() -> None:
    """
    Create all tables and indexes if they do not already exist.
 
    Runs the evacuation_mode migration check FIRST, before the normal
    CREATE TABLE IF NOT EXISTS pass - CREATE TABLE IF NOT EXISTS is a
    no-op against a Casualties table that already exists with the old
    (NOT NULL) column definition, so the migration must happen ahead of
    it, not rely on it.
 
    The resource-movement-metadata migration (Phase 6A) runs AFTER the
    CREATE TABLE IF NOT EXISTS pass instead, since ALTER TABLE ADD COLUMN
    requires the table to already exist - for a fresh database that pass
    already creates Ambulances/Helicopters with these columns present, so
    the migration below simply finds nothing missing and does nothing.
 
    Index (re)creation always runs last so any indexes dropped by the
    evacuation_mode migration's table-recreation are restored.
    """
    with get_connection() as conn:
        if _casualties_needs_evacuation_mode_migration(conn):
            _migrate_casualties_evacuation_mode_nullable(conn)
 
        for statement in SCHEMA_STATEMENTS:
            conn.execute(statement)
 
        _migrate_resource_movement_metadata(conn)
 
        for statement in INDEX_STATEMENTS:
            conn.execute(statement)
    logger.info("Schema created (or already present).")
 
 
def seed_facilities_and_beds() -> None:
    """
    Insert the four fixed facilities (RAP, ADS, HMV, FDC) and their beds,
    only if they do not already exist. Safe to call on every app startup.
    """
    with get_connection() as conn:
        existing = conn.execute("SELECT COUNT(*) AS c FROM Facilities").fetchone()["c"]
        if existing > 0:
            logger.info("Facilities already seeded, skipping.")
            return
 
        for code in FACILITY_ORDER:
            cfg = FACILITY_CONFIG[code]
            cursor = conn.execute(
                """
                INSERT INTO Facilities (
                    facility_name, facility_code, capacity, occupied_beds,
                    available_beds, queue_length, treatment_duration_hours,
                    facility_status, grid_x, grid_y
                ) VALUES (?, ?, ?, 0, ?, 0, ?, ?, ?, ?)
                """,
                (
                    cfg["facility_name"],
                    code,
                    cfg["capacity"],
                    cfg["capacity"],
                    cfg["treatment_duration_hours"],
                    FACILITY_STATUS_OPERATIONAL,
                    cfg["grid_x"],
                    cfg["grid_y"],
                ),
            )
            facility_id = cursor.lastrowid
 
            bed_rows = [
                (facility_id, bed_number, "Available", None, None, None)
                for bed_number in range(1, cfg["capacity"] + 1)
            ]
            conn.executemany(
                """
                INSERT INTO Beds (
                    facility_id, bed_number, status,
                    current_casualty, occupied_since, expected_release_time
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                bed_rows,
            )
        logger.info("Facilities and beds seeded.")
 
 
def _backfill_missing_vehicle_positions(conn) -> None:
    """
    Phase 6A.1: one-time backfill for databases seeded BEFORE
    VEHICLE_INITIAL_POSITIONS existed (or any row that otherwise ended up
    with a NULL grid_x/grid_y). Sets grid_x/grid_y to the vehicle type's
    deterministic initial position, but ONLY for rows still NULL - it
    never overwrites a position a later phase may already be tracking
    (e.g. a vehicle mid-dispatch that a future phase has started moving).
 
    Touches only grid_x/grid_y. Does not touch status, release_time,
    assigned_casualty, dispatch_time, origin_grid_x, or origin_grid_y -
    no transport behavior is affected by this backfill.
    """
    amb_pos = VEHICLE_INITIAL_POSITIONS["Ambulance"]
    ambulances_updated = conn.execute(
        "UPDATE Ambulances SET grid_x = ?, grid_y = ? WHERE grid_x IS NULL OR grid_y IS NULL",
        (amb_pos["grid_x"], amb_pos["grid_y"]),
    ).rowcount
 
    heli_pos = VEHICLE_INITIAL_POSITIONS["Helicopter"]
    helicopters_updated = conn.execute(
        "UPDATE Helicopters SET grid_x = ?, grid_y = ? WHERE grid_x IS NULL OR grid_y IS NULL",
        (heli_pos["grid_x"], heli_pos["grid_y"]),
    ).rowcount
 
    if ambulances_updated or helicopters_updated:
        logger.info(
            "Backfilled initial grid_x/grid_y for %d ambulance(s) and %d helicopter(s) "
            "that predated VEHICLE_INITIAL_POSITIONS.",
            ambulances_updated,
            helicopters_updated,
        )
 
 
def seed_resource_fleets() -> None:
    """
    Insert the fixed pools of ambulances, helicopters, and medical teams.
 
    Phase 6A.1: ambulances/helicopters are now seeded with grid_x/grid_y
    already set to their type's deterministic initial position
    (VEHICLE_INITIAL_POSITIONS), so every vehicle has a valid position
    from the moment it exists - not just after some future phase starts
    tracking movement. If fleets already exist (e.g. an app restart, or
    a database seeded before this fix), _backfill_missing_vehicle_positions()
    still runs so any pre-existing NULL row gets a valid position too.
    """
    with get_connection() as conn:
        existing = conn.execute("SELECT COUNT(*) AS c FROM Ambulances").fetchone()["c"]
        if existing > 0:
            _backfill_missing_vehicle_positions(conn)
            logger.info("Resource fleets already seeded, skipping (existing rows backfilled if needed).")
            return
 
        amb_pos = VEHICLE_INITIAL_POSITIONS["Ambulance"]
        ambulance_rows = [
            (f"AMB-{i:02d}", "Available", amb_pos["grid_x"], amb_pos["grid_y"])
            for i in range(1, AMBULANCE_FLEET_SIZE + 1)
        ]
        conn.executemany(
            "INSERT INTO Ambulances (call_sign, status, grid_x, grid_y) VALUES (?, ?, ?, ?)",
            ambulance_rows,
        )
 
        heli_pos = VEHICLE_INITIAL_POSITIONS["Helicopter"]
        helicopter_rows = [
            (f"HELI-{i:02d}", "Available", heli_pos["grid_x"], heli_pos["grid_y"])
            for i in range(1, HELICOPTER_FLEET_SIZE + 1)
        ]
        conn.executemany(
            "INSERT INTO Helicopters (call_sign, status, grid_x, grid_y) VALUES (?, ?, ?, ?)",
            helicopter_rows,
        )
 
        team_rows = [
            (f"MED-TEAM-{i:02d}", "Available", MEDICAL_TEAM_ROLES[i % len(MEDICAL_TEAM_ROLES)])
            for i in range(1, MEDICAL_TEAM_COUNT + 1)
        ]
        conn.executemany(
            "INSERT INTO Medical_Teams (team_name, status, specialization) VALUES (?, ?, ?)",
            team_rows,
        )
        logger.info("Resource fleets seeded.")
 
 
def initialize_database() -> None:
    """Full idempotent initialization: schema + seed data. Call this at app startup."""
    create_schema()
    seed_facilities_and_beds()
    seed_resource_fleets()
 
 
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    initialize_database()
    print(f"Database initialized at: {DATABASE_PATH}")