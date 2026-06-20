import re
from datetime import datetime
from typing import Optional, Tuple
from dateutil import parser as dateutil_parser


def parse_date(date_str: str) -> Optional[Tuple[str, int, int, int]]:
    if not date_str:
        return None
    try:
        dt = dateutil_parser.parse(date_str, fuzzy=True)
        quarter = (dt.month - 1) // 3 + 1
        return dt.strftime("%Y-%m-%d"), dt.year, dt.month, quarter
    except (ValueError, TypeError):
        return None


def extract_date_from_text(text: str) -> Optional[str]:
    patterns = [
        r'\d{1,2}\s+(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4}',
        r'(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4}',
        r'\d{4}-\d{2}-\d{2}',
        r'\d{1,2}/\d{1,2}/\d{4}',
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(0)
    return None


def clean_text(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r'\s+', ' ', text)
    text = text.strip()
    return text


def extract_vessel_name(text: str) -> Optional[str]:
    patterns = [
        r"(?:vessel|ship|mv|m\.v\.|ss)\s+['\"]?([A-Z][A-Za-z\s\-]+)['\"]?",
        r"(?:aboard|on board)\s+(?:the\s+)?([A-Z][A-Za-z\s\-]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return clean_text(match.group(1))
    return None


def extract_imo_number(text: str) -> Optional[str]:
    match = re.search(r'IMO\s*(?:number|no\.?)?\s*:?\s*(\d{7})', text, re.IGNORECASE)
    if match:
        return match.group(1)
    return None


def categorize_severity(fatalities: int, injuries: int, env_impact: bool = False) -> str:
    if fatalities > 0:
        return "Fatal"
    if injuries > 2 or env_impact:
        return "High"
    if injuries > 0:
        return "Moderate"
    return "Low"


def extract_keywords(text: str, max_keywords: int = 8) -> str:
    maritime_terms = [
        "grounding", "collision", "fire", "explosion", "man overboard", "MOB",
        "capsize", "flooding", "machinery failure", "structural failure",
        "DP", "dynamic positioning", "mooring", "anchor", "propulsion",
        "navigation", "ECDIS", "radar", "AIS", "VHF", "GMDSS",
        "fatigue", "PPE", "fall", "crush", "struck by", "dropped object",
        "lifting", "crane", "heavy lift", "pipelay", "diving",
        "helicopter", "medevac", "SAR", "rescue",
        "pollution", "oil spill", "chemical", "bunker",
        "weather", "storm", "wave", "wind", "ice",
        "human error", "procedural", "training", "communication",
    ]
    found = []
    text_lower = text.lower() if text else ""
    for term in maritime_terms:
        if term.lower() in text_lower and term not in found:
            found.append(term)
            if len(found) >= max_keywords:
                break
    return ", ".join(found) if found else None
