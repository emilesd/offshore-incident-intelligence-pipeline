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
    parse_date, clean_text, extract_keywords,
)
from pipeline.utils.pdf_extractor import extract_text_from_pdf, cleanup_pdf

logger = logging.getLogger(__name__)


class IMCADPScraper(BaseScraper):
    SOURCE_NAME = "IMCA DP Incidents"
    BASE_URL = "https://www.imca-int.com/resources/dp/dp-incidents/"

    def discover_reports(self) -> List[Dict[str, str]]:
        reports = []
        response = self.fetch_page(self.BASE_URL)
        if not response:
            return reports

        soup = BeautifulSoup(response.text, "lxml")

        links = soup.select("a[href*='dp-incident'], a[href*='dp-event']")
        if not links:
            links = soup.select(".resource-item a, .listing-item a, article a, .card a")
        if not links:
            links = soup.select("a[href*='/resources/dp/']")

        for link in links:
            href = link.get("href", "")
            if not href or href == self.BASE_URL:
                continue
            if not href.startswith("http"):
                href = "https://www.imca-int.com" + href

            title = clean_text(link.get_text())
            if title and len(title) > 3:
                reports.append({"url": href, "title": title})

        seen = set()
        unique_reports = []
        for r in reports:
            if r["url"] not in seen:
                seen.add(r["url"])
                unique_reports.append(r)

        logger.info("IMCA DP: discovered %d report links", len(unique_reports))
        return unique_reports

    def extract_report(self, link_info: Dict[str, str]) -> Optional[Dict[str, Any]]:
        url = link_info["url"]
        title = link_info.get("title", "")

        response = self.fetch_page(url)
        if not response:
            return None

        soup = BeautifulSoup(response.text, "lxml")

        narrative = self._extract_narrative(soup)
        date_str = self._extract_date(soup)
        vessel_type = self._extract_vessel_type(title, narrative)
        dp_class = self._extract_dp_class(title, narrative)
        lessons = self._extract_lessons(soup)

        date_info = parse_date(date_str) if date_str else None
        year = date_info[1] if date_info else None
        month = date_info[2] if date_info else None
        quarter = date_info[3] if date_info else None
        formatted_date = date_info[0] if date_info else None

        pdf_text = self._try_extract_pdf(soup)
        full_text = (narrative or "") + " " + (pdf_text or "")

        keywords = extract_keywords(full_text)
        sub_category = self._determine_sub_category(title, full_text)

        seq = self.db.get_next_serial_number()
        year_val = year or 2026
        incident_id = f"IMCA-DP-{year_val}-{seq:03d}"

        record = self.build_incident_record(
            incident_id=incident_id,
            incident_title=title,
            incident_date=formatted_date,
            year=year,
            month=month,
            quarter=quarter,
            source_organization=self.SOURCE_NAME,
            source_link=url,
            report_type="DP Incident Report",
            vessel_type=vessel_type,
            dp_class=dp_class,
            incident_category="DP Incident",
            sub_category=sub_category,
            narrative_summary=narrative[:2000] if narrative else None,
            lessons_learned=lessons,
            keywords=keywords if keywords else "DP, Dynamic Positioning",
            short_description=title,
        )
        return record

    def _extract_narrative(self, soup: BeautifulSoup) -> Optional[str]:
        content_areas = soup.select(
            ".entry-content, .post-content, .resource-content, "
            "article .content, main .content, .single-resource"
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

    def _extract_date(self, soup: BeautifulSoup) -> Optional[str]:
        time_el = soup.select_one("time[datetime]")
        if time_el:
            return time_el["datetime"]

        date_el = soup.select_one(".date, .publish-date, .meta-date")
        if date_el:
            return clean_text(date_el.get_text())
        return None

    def _extract_vessel_type(self, title: str, text: str) -> str:
        combined = (title + " " + (text or "")).lower()
        types = {
            "drillship": "Drillship",
            "semi-sub": "Semi-Submersible",
            "fpso": "FPSO",
            "psv": "PSV",
            "ahts": "AHTS",
            "csv": "CSV",
            "pipelay": "Pipelay Vessel",
            "heavy lift": "Heavy Lift Vessel",
            "dive support": "Dive Support Vessel",
            "construction": "Construction Vessel",
        }
        for key, value in types.items():
            if key in combined:
                return value
        return "DP Vessel"

    def _extract_dp_class(self, title: str, text: str) -> str:
        combined = (title + " " + (text or ""))
        match = re.search(r'(?:DP|dp)\s*(?:class\s*)?([123])', combined)
        if match:
            return f"DP{match.group(1)}"
        if "dp2" in combined.lower() or "dp-2" in combined.lower():
            return "DP2"
        if "dp3" in combined.lower() or "dp-3" in combined.lower():
            return "DP3"
        return "Unknown"

    def _extract_lessons(self, soup: BeautifulSoup) -> Optional[str]:
        headings = soup.find_all(["h2", "h3", "h4", "strong"])
        for heading in headings:
            text = heading.get_text().lower()
            if any(kw in text for kw in ["lesson", "learning", "action", "recommendation"]):
                parts = []
                sibling = heading.find_next_sibling()
                while sibling and sibling.name not in ["h2", "h3", "h4"]:
                    t = clean_text(sibling.get_text())
                    if t:
                        parts.append(t)
                    sibling = sibling.find_next_sibling()
                    if len(parts) >= 5:
                        break
                if parts:
                    return " ".join(parts)
        return None

    def _determine_sub_category(self, title: str, text: str) -> str:
        combined = (title + " " + (text or "")).lower()
        sub_cats = {
            "drive-off": "Drive-Off",
            "drift-off": "Drift-Off",
            "position loss": "Position Loss",
            "excursion": "Excursion",
            "reference": "Reference System Failure",
            "thruster": "Thruster Failure",
            "power": "Power Failure",
            "generator": "Power Failure",
            "blackout": "Power Failure",
            "sensor": "Sensor Failure",
            "wind": "Environmental Exceedance",
            "current": "Environmental Exceedance",
        }
        for key, value in sub_cats.items():
            if key in combined:
                return value
        return "DP Event"

    def _try_extract_pdf(self, soup: BeautifulSoup) -> Optional[str]:
        pdf_links = soup.select("a[href$='.pdf']")
        if not pdf_links:
            return None

        pdf_url = pdf_links[0]["href"]
        if not pdf_url.startswith("http"):
            pdf_url = "https://www.imca-int.com" + pdf_url

        filename = pdf_url.split("/")[-1].split("?")[0]
        save_path = os.path.join(PDF_DOWNLOAD_DIR, filename)

        downloaded = self.fetch_pdf(pdf_url, save_path)
        if downloaded:
            text = extract_text_from_pdf(save_path)
            cleanup_pdf(save_path)
            return text
        return None
