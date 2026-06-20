import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)


def extract_text_from_pdf(pdf_path: str) -> Optional[str]:
    try:
        import pdfplumber
        text_parts = []
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text_parts.append(page_text)
        return "\n".join(text_parts)
    except Exception as e:
        logger.error("PDF extraction failed for %s: %s", pdf_path, e)
        return None


def extract_tables_from_pdf(pdf_path: str) -> list:
    try:
        import pdfplumber
        tables = []
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                page_tables = page.extract_tables()
                if page_tables:
                    tables.extend(page_tables)
        return tables
    except Exception as e:
        logger.error("PDF table extraction failed for %s: %s", pdf_path, e)
        return []


def cleanup_pdf(pdf_path: str):
    try:
        if os.path.exists(pdf_path):
            os.remove(pdf_path)
    except OSError as e:
        logger.warning("Could not remove PDF %s: %s", pdf_path, e)
