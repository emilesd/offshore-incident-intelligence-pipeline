"""
Offshore Incident Intelligence Pipeline
========================================
Main entry point for running the data pipeline.

Usage:
    python run_pipeline.py --run-all          Run all scrapers once
    python run_pipeline.py --run <source>     Run a specific scraper
    python run_pipeline.py --schedule         Start the scheduler (continuous)
    python run_pipeline.py --status           Show pipeline status
    python run_pipeline.py --export           Export data to Excel
"""

import argparse
import logging
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import LOGS_DIR, DATA_DIR
from pipeline.database import Database
from pipeline.scheduler import run_all_scrapers, run_scraper, start_scheduler, SCRAPER_MAP
from pipeline.monitor import PipelineMonitor

LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"


def setup_logging(level=logging.INFO):
    log_file = os.path.join(LOGS_DIR, "pipeline.log")
    logging.basicConfig(
        level=level,
        format=LOG_FORMAT,
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )


def export_to_excel():
    try:
        import openpyxl
        from openpyxl import Workbook
    except ImportError:
        print("openpyxl required: pip install openpyxl")
        return

    db = Database()
    conn = db._get_connection()
    try:
        cursor = conn.execute("SELECT * FROM incidents ORDER BY serial_number")
        rows = cursor.fetchall()
        columns = [desc[0] for desc in cursor.description]
    finally:
        conn.close()

    wb = Workbook()
    ws = wb.active
    ws.title = "Incident Database"

    ws.append(columns)
    for row in rows:
        ws.append(list(row))

    output_path = os.path.join(DATA_DIR, "offshore_incidents_export.xlsx")
    wb.save(output_path)
    print(f"Exported {len(rows)} incidents to {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Offshore Incident Intelligence Data Pipeline"
    )
    parser.add_argument("--run-all", action="store_true",
                        help="Run all scrapers once")
    parser.add_argument("--run", type=str, choices=list(SCRAPER_MAP.keys()),
                        help="Run a specific scraper")
    parser.add_argument("--schedule", action="store_true",
                        help="Start the automated scheduler")
    parser.add_argument("--status", action="store_true",
                        help="Show pipeline status report")
    parser.add_argument("--export", action="store_true",
                        help="Export database to Excel")
    parser.add_argument("--verbose", action="store_true",
                        help="Enable debug logging")

    args = parser.parse_args()

    log_level = logging.DEBUG if args.verbose else logging.INFO
    setup_logging(log_level)

    if args.status:
        monitor = PipelineMonitor()
        monitor.print_status()
        return

    if args.export:
        export_to_excel()
        return

    if args.run:
        run_scraper(args.run)
        return

    if args.run_all:
        run_all_scrapers()
        return

    if args.schedule:
        print("Starting automated pipeline scheduler...")
        print("Press Ctrl+C to stop")
        start_scheduler(blocking=True)
        return

    parser.print_help()


if __name__ == "__main__":
    main()
