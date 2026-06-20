import logging
import json
from datetime import datetime
from typing import Dict, List

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import LOGS_DIR
from pipeline.database import Database

logger = logging.getLogger(__name__)


class PipelineMonitor:
    def __init__(self, db: Database = None):
        self.db = db or Database()

    def get_status_report(self) -> Dict:
        total_incidents = self.db.get_incident_count()
        scrape_stats = self.db.get_scrape_stats()

        return {
            "timestamp": datetime.utcnow().isoformat(),
            "total_incidents_in_db": total_incidents,
            "recent_scrape_runs": scrape_stats,
        }

    def print_status(self):
        report = self.get_status_report()
        print("\n" + "=" * 60)
        print("  OFFSHORE INCIDENT INTELLIGENCE PIPELINE - STATUS")
        print("=" * 60)
        print(f"  Timestamp: {report['timestamp']}")
        print(f"  Total incidents in database: {report['total_incidents_in_db']}")
        print("-" * 60)
        print("  Recent Scrape Runs:")
        print("-" * 60)

        for run in report["recent_scrape_runs"]:
            print(f"    Source: {run['source']}")
            print(f"    Status: {run['status']}")
            print(f"    Found: {run['records_found']} | "
                  f"Inserted: {run['records_inserted']} | "
                  f"Duplicates: {run['records_duplicates']}")
            print(f"    Completed: {run['completed_at']}")
            print()

        print("=" * 60)

    def export_report(self, filepath: str = None):
        if filepath is None:
            filepath = os.path.join(
                LOGS_DIR,
                f"pipeline_report_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
            )

        report = self.get_status_report()
        with open(filepath, "w") as f:
            json.dump(report, f, indent=2)
        logger.info("Report exported to %s", filepath)
        return filepath

    def get_source_summary(self) -> List[Dict]:
        conn = self.db._get_connection()
        try:
            cursor = conn.execute(
                """SELECT source_organization, COUNT(*) as count,
                          MIN(incident_date) as earliest,
                          MAX(incident_date) as latest
                   FROM incidents
                   GROUP BY source_organization"""
            )
            return [dict(row) for row in cursor.fetchall()]
        finally:
            conn.close()

    def get_dedup_report(self) -> List[Dict]:
        conn = self.db._get_connection()
        try:
            cursor = conn.execute(
                """SELECT action, COUNT(*) as count, reason
                   FROM dedup_logs
                   GROUP BY action, reason
                   ORDER BY count DESC"""
            )
            return [dict(row) for row in cursor.fetchall()]
        finally:
            conn.close()
