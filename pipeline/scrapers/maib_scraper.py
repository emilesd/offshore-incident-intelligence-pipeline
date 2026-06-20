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
    parse_date, clean_text, extract_keywords, categorize_severity,
    extract_imo_number, extract_date_from_text,
)
from pipeline.utils.pdf_extractor import extract_text_from_pdf, cleanup_pdf

logger = logging.getLogger(__name__)


class MAIBScraper(BaseScraper):
    SOURCE_NAME = "MAIB"
    BASE_URL = "https://www.gov.uk/maib-reports"
    LISTING_URL = "https://www.gov.uk/maib-reports"

    def discover_reports(self) -> List[Dict[str, str]]:
        reports = []
        page = 1
        max_pages = 5

        while page <= max_pages:
            url = f"{self.LISTING_URL}?page={page}"
            response = self.fetch_page(url)
            if not response:
                break

            soup = BeautifulSoup(response.text, "lxml")
            items = soup.select("li.gem-c-document-list__item")

            if not items:
                items = soup.select(".gem-c-document-list__item-title a")
                if not items:
                    break

            found_new = False
            for item in items:
                link_tag = item.select_one("a") if item.name == "li" else item
                if link_tag and link_tag.get("href"):
                    href = link_tag["href"]
                    if not href.startswith("http"):
                        href = "https://www.gov.uk" + href
                    title = clean_text(link_tag.get_text())
                    reports.append({"url": href, "title": title})
                    found_new = True

            if not found_new:
                break
            page += 1

        logger.info("MAIB: discovered %d report links", len(reports))
        return reports

    def extract_report(self, link_info: Dict[str, str]) -> Optional[Dict[str, Any]]:
        url = link_info["url"]
        title = link_info.get("title", "")

        response = self.fetch_page(url)
        if not response:
            return None

        soup = BeautifulSoup(response.text, "lxml")

        narrative = self._extract_narrative(soup)
        date_str = self._extract_date(soup)
        vessel_name = self._extract_vessel_name(soup, title)
        vessel_type = self._extract_vessel_type(soup, narrative)

        date_info = parse_date(date_str) if date_str else None
        year = date_info[1] if date_info else None
        month = date_info[2] if date_info else None
        quarter = date_info[3] if date_info else None
        formatted_date = date_info[0] if date_info else None

        pdf_text = self._try_extract_pdf(soup, url)
        full_text = (narrative or "") + " " + (pdf_text or "")

        imo = extract_imo_number(full_text)
        incident_category = self._determine_category(title, full_text)
        keywords = extract_keywords(full_text)

        incident_id = self._generate_id(title, year)

        record = self.build_incident_record(
            incident_id=incident_id,
            incident_title=title,
            incident_date=formatted_date,
            year=year,
            month=month,
            quarter=quarter,
            region=self._extract_region(full_text),
            country=self._extract_country(full_text),
            source_organization=self.SOURCE_NAME,
            source_link=url,
            report_type="Investigation Report",
            vessel_name=vessel_name,
            imo_number=imo or "Unknown",
            vessel_type=vessel_type,
            incident_category=incident_category,
            narrative_summary=narrative[:2000] if narrative else None,
            keywords=keywords,
            short_description=title,
        )
        return record

    def _extract_narrative(self, soup: BeautifulSoup) -> Optional[str]:
        content = soup.select_one(".govspeak")
        if content:
            paragraphs = content.find_all("p")
            text = " ".join([clean_text(p.get_text()) for p in paragraphs[:10]])
            return text
        return None

    def _extract_date(self, soup: BeautifulSoup) -> Optional[str]:
        dts = soup.find_all("dt")
        for dt in dts:
            if "date of occurrence" in dt.get_text().lower():
                dd = dt.find_next_sibling("dd")
                if dd:
                    return clean_text(dd.get_text())

        time_el = soup.select_one("time")
        if time_el and time_el.get("datetime"):
            return time_el["datetime"]

        date_el = soup.select_one("dl.gem-c-metadata__list dd")
        if date_el:
            return clean_text(date_el.get_text())
        return None

    def _extract_vessel_name(self, soup: BeautifulSoup, title: str) -> str:
        patterns = [
            r"(?:from|of|aboard)\s+(?:the\s+)?([A-Z][A-Za-z\s\-']+?)(?:\s+during|\s+with|\s+in|\s*$)",
            r"(?:vessel|ship)\s+([A-Z][A-Za-z\s\-']+)",
        ]
        for pattern in patterns:
            match = re.search(pattern, title)
            if match:
                name = match.group(1).strip()
                if len(name) > 2 and name.lower() not in ("the", "a", "an"):
                    return name
        return "Unknown"

    def _extract_vessel_type(self, soup: BeautifulSoup, text: str) -> str:
        types_map = {
            "fishing vessel": "Fishing Vessel",
            "cargo": "Cargo Ship",
            "tanker": "Tanker",
            "passenger": "Passenger Vessel",
            "ferry": "Passenger/Car Ferry",
            "bulk carrier": "Bulk Carrier",
            "container": "Container Ship",
            "tug": "Tug",
            "yacht": "Yacht",
            "ro-ro": "Ro-Ro",
        }
        if text:
            text_lower = text.lower()
            for key, value in types_map.items():
                if key in text_lower:
                    return value
        return "Unknown"

    def _determine_category(self, title: str, text: str) -> str:
        title_lower = title.lower()
        title_categories = [
            ("man overboard", "Man Overboard"),
            ("fall overboard", "Man Overboard"),
            ("capsize", "Capsize"),
            ("grounding", "Grounding"),
            ("collision", "Collision"),
            ("fire", "Fire/Explosion"),
            ("explosion", "Fire/Explosion"),
            ("flooding", "Flooding"),
            ("sinking", "Sinking"),
            ("foundering", "Sinking"),
            ("machinery", "Machinery Failure"),
            ("structural", "Structural Failure"),
            ("mooring", "Mooring Failure"),
            ("dropped object", "Dropped Object"),
            ("personal injury", "Personnel Injury"),
            ("fatal accident", "Personnel Injury"),
            ("crush", "Personnel Injury"),
            ("rescue craft", "Lifesaving Appliance Incident"),
            ("lifeboat", "Lifesaving Appliance Incident"),
            ("propulsion", "Machinery Failure"),
            ("tow rope", "Mooring Failure"),
        ]
        for key, value in title_categories:
            if key in title_lower:
                return value

        if text:
            text_lower = text[:500].lower()
            for key, value in title_categories[:10]:
                if key in text_lower:
                    return value
        return "Other"

    def _extract_region(self, text: str) -> str:
        if not text:
            return "Unknown"
        text_lower = text.lower()
        if any(w in text_lower for w in ["uk", "england", "scotland", "wales", "channel"]):
            return "Europe"
        if any(w in text_lower for w in ["north sea", "norwegian", "baltic"]):
            return "Europe"
        return "Unknown"

    def _extract_country(self, text: str) -> str:
        if not text:
            return "Unknown"
        countries = {
            "scotland": "Scotland, UK",
            "england": "England, UK",
            "wales": "Wales, UK",
            "united kingdom": "UK",
            "norway": "Norway",
            "sweden": "Sweden",
            "denmark": "Denmark",
            "germany": "Germany",
            "netherlands": "Netherlands",
        }
        text_lower = text.lower()
        for key, value in countries.items():
            if key in text_lower:
                return value
        return "UK"

    def _try_extract_pdf(self, soup: BeautifulSoup, page_url: str) -> Optional[str]:
        pdf_links = soup.select("a[href$='.pdf']")
        if not pdf_links:
            return None

        pdf_url = pdf_links[0]["href"]
        if not pdf_url.startswith("http"):
            pdf_url = "https://www.gov.uk" + pdf_url

        filename = pdf_url.split("/")[-1]
        save_path = os.path.join(PDF_DOWNLOAD_DIR, filename)

        downloaded = self.fetch_pdf(pdf_url, save_path)
        if downloaded:
            text = extract_text_from_pdf(save_path)
            cleanup_pdf(save_path)
            return text
        return None

    def _generate_id(self, title: str, year: int) -> str:
        prefix_map = {
            "grounding": "GRD",
            "collision": "COL",
            "fire": "FIR",
            "man overboard": "MOB",
            "fall overboard": "MOB",
            "machinery": "MCH",
            "capsize": "CAP",
            "flooding": "FLD",
            "rescue": "LSA",
            "lifeboat": "LSA",
        }
        title_lower = title.lower()
        prefix = "INC"
        for key, value in prefix_map.items():
            if key in title_lower:
                prefix = value
                break

        year_val = year or 2025
        seq = self.db.get_next_serial_number()
        return f"{prefix}-{year_val}-{seq:03d}"
