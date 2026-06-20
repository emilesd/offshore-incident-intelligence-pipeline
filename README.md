# Offshore Incident Intelligence Pipeline

Automated data pipeline that monitors maritime safety investigation websites, extracts incident reports, and stores structured data in a SQLite database.

## Data Sources

| # | Source | URL | Content |
|---|--------|-----|---------|
| 1 | MAIB (UK) | [gov.uk/maib-reports](https://www.gov.uk/maib-reports) | Maritime accident investigation reports |
| 2 | Swedish Accident Investigation Authority | [shk.se](https://shk.se/engelska/the-swedish-accident-investigation-authority/search-investigation/) | Maritime transport investigations |
| 3 | The Nautical Institute | [nautinst.org](https://www.nautinst.org/technical-resources/resource-library.html) | Safety flashes and MARS reports |
| 4 | IMCA Safety Flashes | [imca-int.com/safety-flashes](https://www.imca-int.com/resources/safety/safety-flashes/) | Offshore safety alerts |
| 5 | IMCA DP Incidents | [imca-int.com/dp-incidents](https://www.imca-int.com/resources/dp/dp-incidents/) | Dynamic positioning events |

## Setup

### Requirements

- Python 3.10+
- pip

### Installation

```bash
pip install -r requirements.txt
```

## Usage

### Run all scrapers once

```bash
python run_pipeline.py --run-all
```

### Run a specific source

```bash
python run_pipeline.py --run maib
python run_pipeline.py --run shk_sweden
python run_pipeline.py --run nautical_institute
python run_pipeline.py --run imca_safety
python run_pipeline.py --run imca_dp
```

### Start automated scheduler

Runs every 6 hours per source + full daily scrape at 02:00 UTC:

```bash
python run_pipeline.py --schedule
```

### Check pipeline status

```bash
python run_pipeline.py --status
```

### Export database to Excel

```bash
python run_pipeline.py --export
```

Output: `data/offshore_incidents_export.xlsx`

### Enable verbose logging

```bash
python run_pipeline.py --run-all --verbose
```

## Database

SQLite database is stored at `data/incidents.db`. The schema matches the provided template with 59 fields including:

- **Identification**: Serial number, Incident ID, Title, Date
- **Location**: Region, Country, Offshore Basin/Area, Coordinates
- **Source**: Organization, Link, Report Type
- **Vessel**: Name, IMO, Type, DP Class, Flag State, Owner, Operator
- **Incident**: Category, Sub-category, Severity, Fatalities, Injuries
- **Analysis**: Root Cause, Human/Technical/Procedural Factors
- **Outcomes**: Corrective Actions, Lessons Learned, Risk Score
- **Metadata**: Keywords, Analyst Notes, Timestamps

## Key Features

- **Automated monitoring** — detects newly published reports on each run
- **Deduplication** — prevents duplicate records using source URL matching
- **PDF extraction** — downloads and parses PDF investigation reports
- **Audit trail** — logs every scrape run with counts and errors
- **Scalable** — new sources can be added by creating a single scraper class

## Project Structure

```
├── run_pipeline.py              # Main entry point (CLI)
├── config.py                    # Source URLs, settings, paths
├── requirements.txt             # Python dependencies
├── pipeline/
│   ├── database.py              # SQLite schema, CRUD, deduplication
│   ├── scheduler.py             # APScheduler automation
│   ├── monitor.py               # Status reporting
│   ├── scrapers/
│   │   ├── base_scraper.py      # Abstract base class
│   │   ├── maib_scraper.py      # UK MAIB
│   │   ├── shk_sweden_scraper.py
│   │   ├── nautical_institute_scraper.py
│   │   ├── imca_safety_scraper.py
│   │   └── imca_dp_scraper.py
│   └── utils/
│       ├── pdf_extractor.py     # PDF text extraction
│       └── text_parser.py       # Date/keyword/text utilities
├── data/                        # Generated at runtime (gitignored)
│   ├── incidents.db
│   └── offshore_incidents_export.xlsx
└── logs/                        # Runtime logs (gitignored)
    └── pipeline.log
```

## Adding a New Source

1. Create a new file in `pipeline/scrapers/` (e.g., `new_source_scraper.py`)
2. Inherit from `BaseScraper` and implement:
   - `discover_reports()` — returns list of report URLs from the listing page
   - `extract_report()` — extracts structured data from a single report
3. Register it in `pipeline/scheduler.py` → `SCRAPER_MAP`
4. Add configuration in `config.py` → `SOURCES`

## Logs & Monitoring

- Runtime logs: `logs/pipeline.log`
- Scrape history: `scrape_logs` table in the database
- Deduplication audit: `dedup_logs` table in the database
