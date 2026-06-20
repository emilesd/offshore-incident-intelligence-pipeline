import re
import os
import logging
from typing import List, Dict, Any, Optional
from bs4 import BeautifulSoup

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from pipeline.scrapers.base_scraper import BaseScraper
from pipeline.utils.text_parser import (
    parse_date, clean_text, extract_keywords, categorize_severity,
)

logger = logging.getLogger(__name__)


class NauticalInstituteScraper(BaseScraper):
    SOURCE_NAME = "The Nautical Institute"
    BASE_URL = "https://www.nautinst.org/technical-resources/resource-library.html"
    LISTING_URLS = [
        "https://www.nautinst.org/technical-resources/resource-library.html?informationTypes=mars",
        "https://www.nautinst.org/technical-resources/resource-library.html",
    ]

    def discover_reports(self) -> List[Dict[str, str]]:
        reports = []

        for listing_url in self.LISTING_URLS:
            response = self.fetch_page(listing_url)
            if not response:
                continue

            soup = BeautifulSoup(response.text, "lxml")
            links = soup.find_all("a", href=True)

            for link in links:
                href = link.get("href", "")
                if "resources-page/" not in href:
                    continue
                if not href.startswith("http"):
                    href = "https://www.nautinst.org" + href

                title = clean_text(link.get_text())
                if title and len(title) > 5:
                    reports.append({"url": href, "title": title})

        seen = set()
        unique_reports = []
        for r in reports:
            if r["url"] not in seen:
                seen.add(r["url"])
                unique_reports.append(r)

        logger.info("Nautical Institute: discovered %d report links", len(unique_reports))
        return unique_reports

    def extract_report(self, link_info: Dict[str, str]) -> Optional[Dict[str, Any]]:
        url = link_info["url"]
        title = link_info.get("title", "")

        response = self.fetch_page(url)
        if not response:
            return None

        soup = BeautifulSoup(response.text, "lxml")

        narrative = self._extract_narrative(soup)
        date_str = self._extract_date(soup, url)
        lessons = self._extract_lessons(soup)

        date_info = parse_date(date_str) if date_str else None
        year = date_info[1] if date_info else None
        month = date_info[2] if date_info else None
        quarter = date_info[3] if date_info else None
        formatted_date = date_info[0] if date_info else None

        full_text = (narrative or "") + " " + (lessons or "")
        incident_category = self._determine_category(title, full_text)
        keywords = extract_keywords(full_text)

        seq = self.db.get_next_serial_number()
        year_val = year or 2026
        incident_id = f"NI-{year_val}-{seq:03d}"

        record = self.build_incident_record(
            incident_id=incident_id,
            incident_title=title,
            incident_date=formatted_date,
            year=year,
            month=month,
            quarter=quarter,
            source_organization=self.SOURCE_NAME,
            source_link=url,
            report_type="Safety Flash",
            incident_category=incident_category,
            narrative_summary=narrative[:2000] if narrative else None,
            lessons_learned=lessons,
            keywords=keywords,
            short_description=title,
        )
        return record

    def _extract_narrative(self, soup: BeautifulSoup) -> Optional[str]:
        content_areas = soup.select(
            ".resource-content, .entry-content, .post-content, "
            ".content-area, article .content, main .content, .body-content"
        )
        for area in content_areas:
            paragraphs = area.find_all("p")
            if paragraphs:
                text = " ".join([clean_text(p.get_text()) for p in paragraphs[:15]])
                if len(text) > 50:
                    return text

        paragraphs = soup.find_all("p")
        text_parts = []
        for p in paragraphs:
            t = clean_text(p.get_text())
            if len(t) > 30:
                text_parts.append(t)
            if len(text_parts) >= 10:
                break
        return " ".join(text_parts) if text_parts else None

    def _extract_date(self, soup: BeautifulSoup, url: str) -> Optional[str]:
        date_match = re.search(r'(\d{6})', url)
        if date_match:
            code = date_match.group(1)
            try:
                year = 2000 + int(code[:2]) if int(code[:2]) < 50 else 1900 + int(code[:2])
                month = int(code[2:4])
                day = int(code[4:6])
                return f"{year}-{month:02d}-{day:02d}"
            except (ValueError, IndexError):
                pass

        time_el = soup.select_one("time[datetime]")
        if time_el:
            return time_el["datetime"]

        date_el = soup.select_one(".date, .publish-date, .post-date")
        if date_el:
            return clean_text(date_el.get_text())
        return None

    def _extract_lessons(self, soup: BeautifulSoup) -> Optional[str]:
        headings = soup.find_all(["h2", "h3", "h4", "strong"])
        for heading in headings:
            text = heading.get_text().lower()
            if "lesson" in text or "learning" in text or "recommendation" in text:
                sibling = heading.find_next_sibling()
                if sibling:
                    return clean_text(sibling.get_text())
        return None

    def _determine_category(self, title: str, text: str) -> str:
        combined = (title + " " + (text or "")).lower()
        categories = {
            "ppe": "Personnel Injury",
            "eye": "Personnel Injury",
            "fall": "Personnel Injury",
            "slip": "Personnel Injury",
            "crush": "Personnel Injury",
            "struck": "Personnel Injury",
            "dropped object": "Dropped Object",
            "lifting": "Heavy Lift Failure",
            "crane": "Heavy Lift Failure",
            "mooring": "Mooring Failure",
            "grounding": "Grounding",
            "collision": "Collision",
            "fire": "Fire/Explosion",
            "dp": "DP Incident",
        }
        for key, value in categories.items():
            if key in combined:
                return value
        return "Near Miss"
