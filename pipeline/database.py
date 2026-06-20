import sqlite3
import logging
from datetime import datetime
from typing import Optional, Dict, Any, List

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import DB_PATH

logger = logging.getLogger(__name__)

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS incidents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    serial_number INTEGER,
    incident_id TEXT UNIQUE,
    incident_title TEXT,
    incident_date TEXT,
    year INTEGER,
    month INTEGER,
    quarter INTEGER,
    region TEXT,
    country TEXT,
    offshore_basin_area TEXT,
    latitude TEXT,
    longitude TEXT,
    source_organization TEXT,
    source_link TEXT UNIQUE,
    report_type TEXT,
    vessel_name TEXT,
    imo_number TEXT,
    vessel_type TEXT,
    dp_class TEXT,
    flag_state TEXT,
    classification_society TEXT,
    registered_owner TEXT,
    operator TEXT,
    operation_type TEXT,
    ship_operation TEXT,
    voyage_segment TEXT,
    weather TEXT,
    sea_state TEXT,
    visibility TEXT,
    incident_category TEXT,
    sub_category TEXT,
    severity_level TEXT,
    fatalities INTEGER DEFAULT 0,
    injuries INTEGER DEFAULT 0,
    environmental_impact TEXT,
    equipment_damage_usd REAL,
    downtime_days REAL,
    immediate_cause TEXT,
    root_cause_category TEXT,
    human_factor TEXT,
    technical_factor TEXT,
    procedural_factor TEXT,
    management_factor TEXT,
    communication_failure TEXT,
    training_deficiency TEXT,
    fatigue_involved TEXT,
    contractor_involved TEXT,
    barrier_failed TEXT,
    detection_method TEXT,
    narrative_summary TEXT,
    contributing_factors TEXT,
    corrective_actions TEXT,
    lessons_learned TEXT,
    likelihood_score INTEGER,
    consequence_score INTEGER,
    risk_score INTEGER,
    keywords TEXT,
    analyst_notes TEXT,
    short_description TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS scrape_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    status TEXT NOT NULL,
    records_found INTEGER DEFAULT 0,
    records_inserted INTEGER DEFAULT 0,
    records_updated INTEGER DEFAULT 0,
    records_duplicates INTEGER DEFAULT 0,
    error_message TEXT,
    started_at TEXT,
    completed_at TEXT
);

CREATE TABLE IF NOT EXISTS dedup_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    incident_id TEXT,
    duplicate_source_link TEXT,
    action TEXT,
    reason TEXT,
    logged_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_incidents_source_link ON incidents(source_link);
CREATE INDEX IF NOT EXISTS idx_incidents_incident_id ON incidents(incident_id);
CREATE INDEX IF NOT EXISTS idx_incidents_source_org ON incidents(source_organization);
CREATE INDEX IF NOT EXISTS idx_incidents_date ON incidents(incident_date);
CREATE INDEX IF NOT EXISTS idx_incidents_category ON incidents(incident_category);
"""


class Database:
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _init_db(self):
        conn = self._get_connection()
        try:
            conn.executescript(SCHEMA_SQL)
            conn.commit()
            logger.info("Database initialized at %s", self.db_path)
        finally:
            conn.close()

    def incident_exists(self, source_link: str) -> bool:
        conn = self._get_connection()
        try:
            cursor = conn.execute(
                "SELECT 1 FROM incidents WHERE source_link = ?", (source_link,)
            )
            return cursor.fetchone() is not None
        finally:
            conn.close()

    def get_next_serial_number(self) -> int:
        conn = self._get_connection()
        try:
            cursor = conn.execute("SELECT MAX(serial_number) FROM incidents")
            result = cursor.fetchone()[0]
            return (result or 0) + 1
        finally:
            conn.close()

    def insert_incident(self, data: Dict[str, Any]) -> Optional[int]:
        if self.incident_exists(data.get("source_link", "")):
            logger.info("Duplicate skipped: %s", data.get("source_link"))
            self._log_dedup(
                data.get("incident_id"),
                data.get("source_link"),
                "skipped",
                "source_link already exists",
            )
            return None

        data["serial_number"] = self.get_next_serial_number()
        data["created_at"] = datetime.utcnow().isoformat()
        data["updated_at"] = datetime.utcnow().isoformat()

        columns = [k for k in data.keys() if k != "id"]
        placeholders = ", ".join(["?" for _ in columns])
        col_names = ", ".join(columns)

        conn = self._get_connection()
        try:
            cursor = conn.execute(
                f"INSERT INTO incidents ({col_names}) VALUES ({placeholders})",
                [data.get(c) for c in columns],
            )
            conn.commit()
            logger.info("Inserted incident: %s", data.get("incident_id"))
            return cursor.lastrowid
        except sqlite3.IntegrityError as e:
            logger.warning("Integrity error inserting %s: %s", data.get("incident_id"), e)
            return None
        finally:
            conn.close()

    def update_incident(self, source_link: str, data: Dict[str, Any]) -> bool:
        data["updated_at"] = datetime.utcnow().isoformat()
        set_clause = ", ".join([f"{k} = ?" for k in data.keys()])
        values = list(data.values()) + [source_link]

        conn = self._get_connection()
        try:
            conn.execute(
                f"UPDATE incidents SET {set_clause} WHERE source_link = ?", values
            )
            conn.commit()
            return True
        except Exception as e:
            logger.error("Error updating incident: %s", e)
            return False
        finally:
            conn.close()

    def get_all_source_links(self, source_organization: Optional[str] = None) -> List[str]:
        conn = self._get_connection()
        try:
            if source_organization:
                cursor = conn.execute(
                    "SELECT source_link FROM incidents WHERE source_organization = ?",
                    (source_organization,),
                )
            else:
                cursor = conn.execute("SELECT source_link FROM incidents")
            return [row[0] for row in cursor.fetchall()]
        finally:
            conn.close()

    def log_scrape(self, source: str, status: str, records_found: int = 0,
                   records_inserted: int = 0, records_updated: int = 0,
                   records_duplicates: int = 0, error_message: str = None,
                   started_at: str = None, completed_at: str = None):
        conn = self._get_connection()
        try:
            conn.execute(
                """INSERT INTO scrape_logs 
                   (source, status, records_found, records_inserted, records_updated, 
                    records_duplicates, error_message, started_at, completed_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (source, status, records_found, records_inserted, records_updated,
                 records_duplicates, error_message, started_at, completed_at),
            )
            conn.commit()
        finally:
            conn.close()

    def _log_dedup(self, incident_id: str, source_link: str, action: str, reason: str):
        conn = self._get_connection()
        try:
            conn.execute(
                """INSERT INTO dedup_logs (incident_id, duplicate_source_link, action, reason)
                   VALUES (?, ?, ?, ?)""",
                (incident_id, source_link, action, reason),
            )
            conn.commit()
        finally:
            conn.close()

    def get_incident_count(self) -> int:
        conn = self._get_connection()
        try:
            cursor = conn.execute("SELECT COUNT(*) FROM incidents")
            return cursor.fetchone()[0]
        finally:
            conn.close()

    def get_scrape_stats(self) -> List[Dict]:
        conn = self._get_connection()
        try:
            cursor = conn.execute(
                """SELECT source, status, records_found, records_inserted, 
                          records_duplicates, completed_at
                   FROM scrape_logs ORDER BY completed_at DESC LIMIT 20"""
            )
            return [dict(row) for row in cursor.fetchall()]
        finally:
            conn.close()
