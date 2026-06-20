import logging
from datetime import datetime
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.schedulers.background import BackgroundScheduler

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import SOURCES
from pipeline.database import Database
from pipeline.scrapers.maib_scraper import MAIBScraper
from pipeline.scrapers.shk_sweden_scraper import SHKSwedenScraper
from pipeline.scrapers.nautical_institute_scraper import NauticalInstituteScraper
from pipeline.scrapers.imca_safety_scraper import IMCASafetyScraper
from pipeline.scrapers.imca_dp_scraper import IMCADPScraper

logger = logging.getLogger(__name__)

SCRAPER_MAP = {
    "maib": MAIBScraper,
    "shk_sweden": SHKSwedenScraper,
    "nautical_institute": NauticalInstituteScraper,
    "imca_safety": IMCASafetyScraper,
    "imca_dp": IMCADPScraper,
}


def run_scraper(source_key: str):
    logger.info("Scheduled run triggered for: %s", source_key)
    db = Database()
    scraper_class = SCRAPER_MAP.get(source_key)
    if not scraper_class:
        logger.error("Unknown source: %s", source_key)
        return

    scraper = scraper_class(db=db)
    stats = scraper.run()
    logger.info("Completed %s: found=%d, inserted=%d, duplicates=%d",
                source_key, stats["records_found"], stats["records_inserted"],
                stats["records_duplicates"])


def run_all_scrapers():
    logger.info("Running all scrapers at %s", datetime.utcnow().isoformat())
    for source_key in SCRAPER_MAP:
        try:
            run_scraper(source_key)
        except Exception as e:
            logger.error("Error running %s: %s", source_key, e)


def start_scheduler(blocking: bool = True):
    if blocking:
        scheduler = BlockingScheduler()
    else:
        scheduler = BackgroundScheduler()

    for source_key, config in SOURCES.items():
        hours = config.get("schedule_hours", 6)
        scheduler.add_job(
            run_scraper,
            "interval",
            hours=hours,
            args=[source_key],
            id=f"scrape_{source_key}",
            name=f"Scrape {config['name']}",
            max_instances=1,
            replace_existing=True,
        )
        logger.info("Scheduled %s every %d hours", source_key, hours)

    scheduler.add_job(
        run_all_scrapers,
        "cron",
        hour=2, minute=0,
        id="daily_full_scrape",
        name="Daily Full Scrape (02:00 UTC)",
        max_instances=1,
    )

    logger.info("Scheduler started with %d jobs", len(scheduler.get_jobs()))

    if blocking:
        try:
            scheduler.start()
        except (KeyboardInterrupt, SystemExit):
            logger.info("Scheduler stopped")
            scheduler.shutdown()
    else:
        scheduler.start()
        return scheduler
