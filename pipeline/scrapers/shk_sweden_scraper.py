import re
import os
import logging
from typing import List, Dict, Any, Optional
from bs4 import BeautifulSoup

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from config import PDF_DOWNLOAD_DIR
from pipeline.scrapers.base_scraper import BaseScraper
from pipeline.utils.text_parser import (
    parse_date, clean_text, extract_keywords, extract_imo_number,
)
from pipeline.utils.pdf_extractor import extract_text_from_pdf, cleanup_pdf

logger = logging.getLogger(__name__)


class SHKSwedenScraper(BaseScraper):
    SOURCE_NAME = "Swedish Accident Investigation Authority"
    BASE_URL = "https://shk.se/engelska/the-swedish-accident-investigation-authority/search-investigation/"

    def discover_reports(self) -> List[Dict[str, str]]:
        reports = []
        response = self.fetch_page(self.BASE_URL)
        if not response:
            return reports

        soup = BeautifulSoup(response.text, "lxml")

        links = soup.find_all("a", href=True)
        for link in links:
            href = link.get("href", "")
            if "maritime-transport" not in href:
                continue
            if not href.startswith("http"):
                href = "https://shk.se" + href

            title = clean_text(link.get_text())
            if title and len(title) > 5:
                reports.append({"url": href, "title": title})

        seen = set()
        unique_reports = []
        for r in reports:
            if r["url"] not in seen:
                seen.add(r["url"])
                unique_reports.append(r)

        logger.info("SHK Sweden: discovered %d report links", len(unique_reports))
        return unique_reports

    def extract_report(self, link_info: Dict[str, str]) -> Optional[Dict[str, Any]]:
        url = link_info["url"]
        title = link_info.get("title", "")

        response = self.fetch_page(url)
        if not response:
            return None

        soup = BeautifulSoup(response.text, "lxml")

        narrative = self._extract_narrative(soup)
        date_str = self._extract_date(soup, url, title)
        vessel_name = self._extract_vessel_name(title, url)

        date_info = parse_date(date_str) if date_str else None
        year = date_info[1] if date_info else None
        month = date_info[2] if date_info else None
        quarter = date_info[3] if date_info else None
        formatted_date = date_info[0] if date_info else None

        pdf_text = self._try_extract_pdf(soup)
        full_text = (narrative or "") + " " + (pdf_text or "")

        imo = extract_imo_number(full_text)
        incident_category = self._determine_category(title, full_text)
        keywords = extract_keywords(full_text)

        seq = self.db.get_next_serial_number()
        year_val = year or 2025
        incident_id = f"SHK-{year_val}-{seq:03d}"

        record = self.build_incident_record(
            incident_id=incident_id,
            incident_title=title,
            incident_date=formatted_date,
            year=year,
            month=month,
            quarter=quarter,
            region="Europe",
            country="Sweden",
            source_organization=self.SOURCE_NAME,
            source_link=url,
            report_type="Investigation Report",
            vessel_name=vessel_name,
            imo_number=imo or "Unknown",
            incident_category=incident_category,
            narrative_summary=narrative[:2000] if narrative else None,
            keywords=keywords,
            short_description=title,
        )
        return record

    def _extract_narrative(self, soup: BeautifulSoup) -> Optional[str]:
        content_areas = soup.select(".entry-content, .post-content, article, .content, main")
        for area in content_areas:
            paragraphs = area.find_all("p")
            if paragraphs:
                text = " ".join([clean_text(p.get_text()) for p in paragraphs[:15]])
                if len(text) > 50:
                    return text
        return None

    def _extract_date(self, soup: BeautifulSoup, url: str, title: str) -> Optional[str]:
        date_match = re.search(r'(\d{4}-\d{2}-\d{2})', url)
        if date_match:
            return date_match.group(1)

        date_match = re.search(r'(\d{4}-\d{2}-\d{2})', title)
        if date_match:
            return date_match.group(1)

        time_el = soup.select_one("time[datetime]")
        if time_el:
            return time_el["datetime"]
        return None

    def _extract_vessel_name(self, title: str, url: str) -> str:
        url_parts = url.rstrip("/").split("/")[-1]
        date_match = re.match(r'\d{4}-\d{2}-\d{2}-(.*)', url_parts)
        if date_match:
            name_part = date_match.group(1)
            name = name_part.split("---")[0].replace("-", " ").strip()
            if name:
                return name.upper()

        parts = title.split("-")
        if len(parts) > 1:
            return clean_text(parts[0])
        return "Unknown"

    def _determine_category(self, title: str, text: str) -> str:
        combined = (title + " " + (text or "")).lower()
        categories = {
            "grounding": "Grounding",
            "collision": "Collision",
            "fire": "Fire/Explosion",
            "capsize": "Capsize",
            "sinking": "Sinking",
            "man overboard": "Man Overboard",
            "machinery": "Machinery Failure",
        }
        for key, value in categories.items():
            if key in combined:
                return value
        return "Other"

    def _try_extract_pdf(self, soup: BeautifulSoup) -> Optional[str]:
        pdf_links = soup.select("a[href$='.pdf']")
        if not pdf_links:
            return None

        pdf_url = pdf_links[0]["href"]
        if not pdf_url.startswith("http"):
            pdf_url = "https://shk.se" + pdf_url

        filename = pdf_url.split("/")[-1]
        save_path = os.path.join(PDF_DOWNLOAD_DIR, filename)

        downloaded = self.fetch_pdf(pdf_url, save_path)
        if downloaded:
            text = extract_text_from_pdf(save_path)
            cleanup_pdf(save_path)
            return text
        return None
