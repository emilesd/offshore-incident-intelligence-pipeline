import time
import logging
import requests
import hashlib
from abc import ABC, abstractmethod
from datetime import datetime
from typing import List, Dict, Any, Optional

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from config import REQUEST_HEADERS, REQUEST_TIMEOUT, REQUEST_DELAY
from pipeline.database import Database

logger = logging.getLogger(__name__)


class BaseScraper(ABC):
    SOURCE_NAME = "Unknown"
    BASE_URL = ""

    def __init__(self, db: Database = None):
        self.db = db or Database()
        self.session = requests.Session()
        self.session.headers.update(REQUEST_HEADERS)
        self.stats = {
            "records_found": 0,
            "records_inserted": 0,
            "records_updated": 0,
            "records_duplicates": 0,
        }

    def fetch_page(self, url: str, params: dict = None) -> Optional[requests.Response]:
        try:
            time.sleep(REQUEST_DELAY)
            response = self.session.get(url, params=params, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
            return response
        except requests.RequestException as e:
            logger.error("Failed to fetch %s: %s", url, e)
            return None

    def fetch_pdf(self, url: str, save_path: str) -> Optional[str]:
        try:
            time.sleep(REQUEST_DELAY)
            response = self.session.get(url, timeout=REQUEST_TIMEOUT, stream=True)
            response.raise_for_status()
            with open(save_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            return save_path
        except requests.RequestException as e:
            logger.error("Failed to download PDF %s: %s", url, e)
            return None

    def generate_incident_id(self, prefix: str, year: int, sequence: int) -> str:
        return f"{prefix}-{year}-{sequence:03d}"

    def compute_hash(self, text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def build_incident_record(self, **kwargs) -> Dict[str, Any]:
        record = {
            "incident_id": kwargs.get("incident_id"),
            "incident_title": kwargs.get("incident_title"),
            "incident_date": kwargs.get("incident_date"),
            "year": kwargs.get("year"),
            "month": kwargs.get("month"),
            "quarter": kwargs.get("quarter"),
            "region": kwargs.get("region", "Unknown"),
            "country": kwargs.get("country", "Unknown"),
            "offshore_basin_area": kwargs.get("offshore_basin_area", "Unknown"),
            "latitude": kwargs.get("latitude", "Unknown"),
            "longitude": kwargs.get("longitude", "Unknown"),
            "source_organization": kwargs.get("source_organization", self.SOURCE_NAME),
            "source_link": kwargs.get("source_link"),
            "report_type": kwargs.get("report_type", "Unknown"),
            "vessel_name": kwargs.get("vessel_name", "Unknown"),
            "imo_number": kwargs.get("imo_number", "Unknown"),
            "vessel_type": kwargs.get("vessel_type", "Unknown"),
            "dp_class": kwargs.get("dp_class", "N/A"),
            "flag_state": kwargs.get("flag_state", "Unknown"),
            "classification_society": kwargs.get("classification_society", "Unknown"),
            "registered_owner": kwargs.get("registered_owner", "Unknown"),
            "operator": kwargs.get("operator", "Unknown"),
            "operation_type": kwargs.get("operation_type", "Unknown"),
            "ship_operation": kwargs.get("ship_operation", "Unknown"),
            "voyage_segment": kwargs.get("voyage_segment", "Unknown"),
            "weather": kwargs.get("weather", "Unknown"),
            "sea_state": kwargs.get("sea_state", "Unknown"),
            "visibility": kwargs.get("visibility", "Unknown"),
            "incident_category": kwargs.get("incident_category", "Unknown"),
            "sub_category": kwargs.get("sub_category", "Unknown"),
            "severity_level": kwargs.get("severity_level", "Unknown"),
            "fatalities": kwargs.get("fatalities", 0),
            "injuries": kwargs.get("injuries", 0),
            "environmental_impact": kwargs.get("environmental_impact", "Unknown"),
            "equipment_damage_usd": kwargs.get("equipment_damage_usd"),
            "downtime_days": kwargs.get("downtime_days"),
            "immediate_cause": kwargs.get("immediate_cause", "Unknown"),
            "root_cause_category": kwargs.get("root_cause_category", "Unknown"),
            "human_factor": kwargs.get("human_factor", "Unknown"),
            "technical_factor": kwargs.get("technical_factor", "Unknown"),
            "procedural_factor": kwargs.get("procedural_factor", "Unknown"),
            "management_factor": kwargs.get("management_factor", "Unknown"),
            "communication_failure": kwargs.get("communication_failure", "Unknown"),
            "training_deficiency": kwargs.get("training_deficiency", "Unknown"),
            "fatigue_involved": kwargs.get("fatigue_involved", "No"),
            "contractor_involved": kwargs.get("contractor_involved", "No"),
            "barrier_failed": kwargs.get("barrier_failed", "Unknown"),
            "detection_method": kwargs.get("detection_method", "Unknown"),
            "narrative_summary": kwargs.get("narrative_summary"),
            "contributing_factors": kwargs.get("contributing_factors"),
            "corrective_actions": kwargs.get("corrective_actions"),
            "lessons_learned": kwargs.get("lessons_learned"),
            "likelihood_score": kwargs.get("likelihood_score"),
            "consequence_score": kwargs.get("consequence_score"),
            "risk_score": kwargs.get("risk_score"),
            "keywords": kwargs.get("keywords"),
            "analyst_notes": kwargs.get("analyst_notes"),
            "short_description": kwargs.get("short_description"),
        }
        return record

    def calculate_quarter(self, month: int) -> int:
        if month is None:
            return None
        return (month - 1) // 3 + 1

    def run(self) -> Dict[str, int]:
        started_at = datetime.utcnow().isoformat()
        logger.info("Starting scrape for %s", self.SOURCE_NAME)

        try:
            report_links = self.discover_reports()
            self.stats["records_found"] = len(report_links)
            logger.info("Discovered %d reports from %s", len(report_links), self.SOURCE_NAME)

            existing_links = set(self.db.get_all_source_links(self.SOURCE_NAME))

            for link_info in report_links:
                url = link_info if isinstance(link_info, str) else link_info.get("url")
                if url in existing_links:
                    self.stats["records_duplicates"] += 1
                    logger.debug("Skipping existing: %s", url)
                    continue

                try:
                    record = self.extract_report(link_info)
                    if record:
                        result = self.db.insert_incident(record)
                        if result:
                            self.stats["records_inserted"] += 1
                        else:
                            self.stats["records_duplicates"] += 1
                except Exception as e:
                    logger.error("Error extracting %s: %s", url, e)

            completed_at = datetime.utcnow().isoformat()
            self.db.log_scrape(
                source=self.SOURCE_NAME,
                status="success",
                records_found=self.stats["records_found"],
                records_inserted=self.stats["records_inserted"],
                records_updated=self.stats["records_updated"],
                records_duplicates=self.stats["records_duplicates"],
                started_at=started_at,
                completed_at=completed_at,
            )
            logger.info("Completed %s: %s", self.SOURCE_NAME, self.stats)

        except Exception as e:
            completed_at = datetime.utcnow().isoformat()
            self.db.log_scrape(
                source=self.SOURCE_NAME,
                status="error",
                error_message=str(e),
                started_at=started_at,
                completed_at=completed_at,
            )
            logger.error("Scrape failed for %s: %s", self.SOURCE_NAME, e)

        return self.stats

    @abstractmethod
    def discover_reports(self) -> List[Any]:
        """Discover all available report links from the source listing page."""
        pass

    @abstractmethod
    def extract_report(self, link_info: Any) -> Optional[Dict[str, Any]]:
        """Extract structured data from a single report page/PDF."""
        pass
