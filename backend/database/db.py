"""
db.py

Centralized SQLite connection management for BMERMS.
All database access should go through get_connection().
"""

from __future__ import annotations
import sqlite3
from pathlib import Path


# Database file lives at the project root.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DB_PATH = PROJECT_ROOT / "bmerms.db"


def get_connection() -> sqlite3.Connection:
    """
    Return a SQLite connection configured to return sqlite3.Row objects,
    so rows support both index and dict-style access.
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn