import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
LOGS_DIR = os.path.join(BASE_DIR, "logs")
DB_PATH = os.path.join(DATA_DIR, "incidents.db")
PDF_DOWNLOAD_DIR = os.path.join(DATA_DIR, "pdfs")

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(LOGS_DIR, exist_ok=True)
os.makedirs(PDF_DOWNLOAD_DIR, exist_ok=True)

SOURCES = {
    "maib": {
        "name": "MAIB",
        "base_url": "https://www.gov.uk/maib-reports",
        "schedule_hours": 6,
    },
    "shk_sweden": {
        "name": "Swedish Accident Investigation Authority",
        "base_url": "https://shk.se/engelska/the-swedish-accident-investigation-authority/search-investigation/maritime-transport",
        "schedule_hours": 6,
    },
    "nautical_institute": {
        "name": "The Nautical Institute",
        "base_url": "https://www.nautinst.org/resources-page",
        "schedule_hours": 6,
    },
    "imca_safety": {
        "name": "IMCA Safety Flashes",
        "base_url": "https://www.imca-int.com/resources/safety/safety-flashes/",
        "schedule_hours": 6,
    },
    "imca_dp": {
        "name": "IMCA DP Incidents",
        "base_url": "https://www.imca-int.com/resources/dp/dp-incidents/",
        "schedule_hours": 6,
    },
}

REQUEST_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}

REQUEST_TIMEOUT = 30
REQUEST_DELAY = 2  # seconds between requests to be polite
