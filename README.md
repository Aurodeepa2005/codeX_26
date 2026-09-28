# StandardMatch AI

**An AI-Powered Recommendation Engine for Identifying Applicable Indian Standards (IS) for Procurement Specifications**

_Smart India Hackathon 2026 Project_

---

## What It Does

StandardMatch AI takes a natural-language procurement description such as:

> "GI pipes for rural drinking water supply, medium class"

and recommends the most applicable Bureau of Indian Standards (IS) documents — complete with IS number, title, relevance score, scope evidence, lifecycle status (Active/Revised/Withdrawn), and QCO (Quality Control Order) information.

---

## Architecture (10-Phase Build Plan)

| Phase | Component                                        | Status         |
| ----- | ------------------------------------------------ | -------------- |
| 1     | BIS Data Collection & Processing Pipeline        | ✅ In Progress |
| 2     | Semantic Retrieval (sentence embeddings + FAISS) | ⏳ Pending     |
| 3     | BM25 Keyword Retrieval                           | ⏳ Pending     |
| 4     | Hybrid Retrieval                                 | ⏳ Pending     |
| 5     | Cross-Encoder Re-ranking                         | ⏳ Pending     |
| 6     | Standard Lifecycle / Supersession Logic          | ⏳ Pending     |
| 7     | QCO Integration                                  | ⏳ Pending     |
| 8     | FastAPI Backend                                  | ⏳ Pending     |
| 9     | Frontend / UI                                    | ⏳ Pending     |
| 10    | Evaluation & Demo                                | ⏳ Pending     |

---

## Project Structure

```
standardmatch-ai/
├── docs/                          # Project blueprint PDF
├── data/
│   ├── raw/                       # Original scraped/downloaded data (not committed)
│   │   ├── bis/                   # Raw BIS scrape outputs
│   │   ├── qco/                   # Raw QCO data
│   │   └── logs/                  # Collection logs
│   ├── processed/                 # Cleaned, normalized datasets
│   │   ├── standards.csv
│   │   ├── standards.json
│   │   └── qco.csv
│   └── evaluation/                # Evaluation queries and labels
│       ├── test_queries.csv
│       └── labelled_results.csv
├── scripts/                       # Data pipeline scripts
│   ├── collect_bis_standards.py   # Phase 1: BIS scraper
│   ├── clean_standards.py         # Phase 1: Data cleaning
│   ├── validate_dataset.py        # Phase 1: Validation & reporting
│   └── build_dataset.py           # Phase 1: Full pipeline orchestrator
├── src/                           # Application source
│   ├── preprocessing/             # Query preprocessing
│   ├── retrieval/                 # BM25 + FAISS retrieval
│   ├── ranking/                   # Re-ranking logic
│   ├── rules/                     # Lifecycle/QCO rules
│   └── utils/                     # Shared utilities
├── models/                        # Saved ML models (not committed)
├── indexes/                       # FAISS/BM25 indexes (not committed)
│   ├── faiss/
│   └── bm25/
├── backend/                       # FastAPI application (Phase 8)
├── frontend/                      # Web UI (Phase 9)
├── tests/                         # Unit & integration tests
├── requirements.txt
├── .env.example
└── README.md
```

---

## Setup

### 1. Clone and create virtual environment

```bash
git clone <repo-url>
cd standardmatch-ai
python -m venv venv
# Windows:
venv\Scripts\activate
# Linux/Mac:
source venv/bin/activate
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure environment

```bash
cp .env.example .env
# Edit .env as needed
```

---

## Phase 1: Run the Data Pipeline

```bash
# Full pipeline: collect → clean → validate
python scripts/build_dataset.py --category pipes --limit 50

# Or run steps individually:
python scripts/collect_bis_standards.py --category pipes --limit 50
python scripts/clean_standards.py
python scripts/validate_dataset.py
```

Output files:

- `data/processed/standards.csv`
- `data/processed/standards.json`
- `data/raw/logs/` (collection and validation logs)

---

## Data Sources

| Source                                                   | Type                               | Usage                             |
| -------------------------------------------------------- | ---------------------------------- | --------------------------------- |
| [BIS Standards Portal](https://standardsbis.bsbedge.com) | Web scraping (public search pages) | IS metadata, title, status, scope |
| [bis.gov.in](https://www.bis.gov.in)                     | Official website                   | QCO information, lifecycle status |

**Important:** Only publicly visible metadata is collected. Full PDF content is not downloaded. All IS numbers are real and traceable to official BIS sources.

---

## Data Fields

| Field                 | Required | Description                           |
| --------------------- | -------- | ------------------------------------- |
| `is_number`           | ✅       | Standard number (e.g., `IS:1239`)     |
| `title`               | ✅       | Full title of the standard            |
| `scope`               | ✅       | Scope/abstract (used for AI matching) |
| `category`            | ✅       | Procurement category                  |
| `status`              | ✅       | Active / Revised / Withdrawn          |
| `source_url`          | ✅       | URL of source page                    |
| `year`                | Optional | Year of publication                   |
| `ics_code`            | Optional | ICS classification code               |
| `technical_committee` | Optional | BIS technical committee               |
| `superseded_by`       | Optional | IS number that supersedes this one    |
| `supersedes`          | Optional | IS number this one supersedes         |
| `collected_at`        | ✅       | ISO 8601 timestamp of collection      |

---

## Evaluation Metrics (Phase 10)

- Precision@3 — top 3 results correct
- Recall@5 — correct standard in top 5
- Response latency (< 2 seconds target)
- Currency accuracy — correct lifecycle status
- Category coverage

---

## License

Metadata collected from BIS public sources for research/hackathon purposes. Indian Standards are copyright of the Bureau of Indian Standards. This system does not redistribute standards documents.
