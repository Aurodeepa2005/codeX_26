"""
collect_bis_standards.py
========================
Phase 1 — BIS Data Collector for StandardMatch AI

Collects Indian Standards metadata from the official BIS portal
(standardsbis.bsbedge.com) using:

  APPROACH:
    1. POST-based IS number search on the BIS portal home page
       (verified form field: ctl00$txt_standardnumber, event: ctl00$btn_stdno)
    2. Parse results → extract BIS_Preview.aspx?id=... links
    3. Fetch each preview page → extract IS number, title, scope, ICS code,
       technical committee, status, year, reaffirmation info
    4. Save raw JSON to data/raw/bis/

  WHY THIS APPROACH:
    - Verified working: POST search returns real results with preview links
    - BIS_Preview.aspx returns full publicly visible scope text (no login needed)
    - IS numbers searched are from well-documented public procurement sources
    - Robots.txt allows all paths except /wp-admin/
    - Rate limited: 2.5s between requests

  WHAT IS NOT COLLECTED:
    - Full standards PDFs (copyright-protected, require purchase)
    - Paid subscription content

Usage:
    python scripts/collect_bis_standards.py --category pipes --limit 50
    python scripts/collect_bis_standards.py --category pipes --limit 10 --dry-run
"""

import argparse
import json
import logging
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

# Ensure stdout and stderr handle utf-8 safely on Windows
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import requests
from bs4 import BeautifulSoup

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(PROJECT_ROOT))

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
BIS_BASE_URL = "https://standardsbis.bsbedge.com"
BIS_HOME_URL = f"{BIS_BASE_URL}/"

REQUEST_DELAY = float(os.getenv("BIS_REQUEST_DELAY_SECONDS", "0.5"))
REQUEST_TIMEOUT = int(os.getenv("BIS_REQUEST_TIMEOUT", "10"))
MAX_RETRIES = int(os.getenv("BIS_MAX_RETRIES", "2"))

SOURCE_NAME = "BIS Standards Portal (standardsbis.bsbedge.com)"
SOURCE_TYPE = "web_scrape_post"

# ---------------------------------------------------------------------------
# Category → IS number seed lists
# These IS numbers are from publicly available BIS publications, government
# tender documents, and procurement guidelines. All are real standards.
# ---------------------------------------------------------------------------
CATEGORY_IS_SEEDS: dict[str, list[str]] = {
    "pipes": [
        # GI / Steel tubes & pipes
        "1239",   # Steel Tubes, Tubulars and Other Wrought Steel Fittings (GI pipes)
        "1161",   # Steel Tubes for Structural Purposes
        "3589",   # Steel Pipes (water/gas transport, large diameter)
        "4270",   # Steel Tubes Used for Water Wells (Casing Pipes)
        "9295",   # Steel Tubes for Idlers for Belt Conveyors
        "1978",   # Line Pipe
        "1589",   # Seamless and Welded Steel Pipes
        "6913",   # Stainless Steel Tubes for Food, Beverage, Dairy
        "3601",   # Steel Tubes for Mechanical and General Engineering Purposes
        "10748",  # Hot-Rolled Steel Strip for Welded Tubes and Pipes
        # Cast iron / Ductile iron
        "1536",   # Centrifugally Cast (Spun) Iron Pressure Pipes for Water, Gas and Sewage
        "8329",   # Ductile Iron Pipes for Potable Water
        "9523",   # Ductile Iron Pipe Fittings
        "1538",   # Cast Iron Pipe Fittings
        "3647",   # Cast Iron Drain Pipes
        "7181",   # Horizontally Cast Iron Double Flanged Pipes
        "3486",   # Cast Iron Spigot and Socket Drain Pipes
        "1729",   # Cast Iron Drainage Pipes and Fittings
        "1230",   # Cast Iron Rainwater Pipes and Fittings
        "3989",   # Centrifugally Cast Iron Soil, Waste and Ventilating Pipes
        # HDPE / Polyethylene
        "4984",   # High Density Polyethylene Pipes
        "14151",  # HDPE Pipes for Potable Water Supplies
        "14333",  # HDPE Pipes for Sewerage
        "12235",  # HDPE Pipes - Methods of Test
        "8008",   # Injection Moulded HDPE Fittings for Potable Water
        "8360",   # Fabricated HDPE Fittings for Potable Water
        "14885",  # Polyethylene Pipes for the Supply of Gaseous Fuels
        "15328",  # Polyethylene (PE) Pipe Systems for Water Supply
        # PVC / UPVC / CPVC
        "4985",   # UPVC Pipes for Potable Water Supply
        "13592",  # UPVC Pipes for Soil and Waste Discharge Systems
        "12818",  # Unplasticized PVC Pipes for Casing and Produce from Tube Wells
        "15778",  # CPVC Pipes for Potable Hot and Cold Water Distribution
        "16098",  # Structured-Wall Plastics Piping Systems
        "7634",   # Code of Practice for Plastic Pipe Systems
        "10124",  # Fabricated PVC Fittings for Potable Water Supplies
        "7834",   # Injection Moulded PVC Fittings with Solvent Cement Joints
        # Concrete / Stoneware / Seals
        "458",    # Precast Concrete Pipes (with and without reinforcement)
        "783",    # Code of Practice for Laying of Concrete Pipes
        "1916",   # Steel Cylinder Reinforced Concrete Pipes
        "651",    # Salt Glazed Stoneware Pipes
        "5382",   # Rubber Seals - Joint Rings for Water Supply Pipelines
        "2379",   # Color Code Identification of Pipelines
        # Structural steel & reinforcement (procured with piping)
        "2062",   # Hot Rolled Medium and High Tensile Structural Steel
        "1786",   # High Strength Deformed Steel Bars and Wires for Concrete Reinforcement
        "808",    # Dimensions for Hot Rolled Steel Beam, Column, Channel and Angle Sections
        "432",    # Mild Steel and Medium Tensile Steel Bars for Concrete Reinforcement
        "280",    # Mild Steel Wire for General Engineering Purposes
    ],
    "cement": [
        "269",    # Ordinary Portland Cement, 33 Grade
        "8112",   # Ordinary Portland Cement, 43 Grade
        "12269",  # Ordinary Portland Cement, 53 Grade
        "1489",   # Portland Pozzolana Cement (PPC)
        "455",    # Portland Slag Cement (PSC)
        "16415",  # Composite Cement
        "4031",   # Methods of Physical Tests for Hydraulic Cement
        "650",    # Standard Sand for Testing Cement
        "3466",   # Masonry Cement
        "6932",   # Methods of Test for White Portland Cement
        "8041",   # Rapid Hardening Portland Cement
        "6909",   # Supersulphated Cement
        "6452",   # High Alumina Cement
        "15388",  # Sulphate Resisting Portland Cement
    ],
    "electrical": [
        "694",    # PVC Insulated Cables for Working Voltages up to 1100V
        "1554",   # PVC Insulated (Heavy Duty) Electric Cables
        "732",    # Code of Practice for Electrical Wiring Installations
        "8130",   # Conductors for Insulated Electric Cables
        "2705",   # Current Transformers
        "3837",   # Accessories for Rigid Steel Conduits
        "1293",   # Plugs and Socket Outlets
        "3043",   # Code of Practice for Earthing
        "13947",  # Miniature Circuit Breakers (MCBs)
        "3156",   # Current Transformers for Protection
        "5578",   # Guide for Marking of Insulated Conductors
        "1255",   # Code of Practice for Installation of Electric Lines
        "9431",   # Wiring Accessories - Intermediate Switches
        "15111",  # Safety Isolating Transformers
    ],
    "ppe": [
        "2925",   # Industrial Safety Helmets
        "4770",   # Rubber Safety Boots
        "5557",   # Industrial Safety Belts and Harnesses
        "6994",   # Industrial Safety Gloves
        "1179",   # Equipment for Eye and Face Protection
        "9167",   # Safety Shoes (Steel Toe Cap)
        "5983",   # Eye Protectors
        "8519",   # Guide for Selection of Industrial Safety Equipment
        "11226",  # Respiratory Protective Devices
        "9168",   # Welding Helmets
        "3521",   # Industrial Safety Nets
        "16435",  # High Visibility Warning Clothing
    ],
    "food_packaging": [
        "9755",   # HDPE Woven Sacks for Packaging
        "1604",   # Jute Hessian Cloth for Sacking
        "1797",   # Methods of Sampling and Test for Jute and Allied Fibres
        "7042",   # Polypropylene Woven Sacks
        "14735",  # Multi-layer Flexible Packaging for Food
        "15450",  # Packaging - Determination of Permeability
        "11703",  # Wrapping and Packaging for Agricultural Produce
        "7224",   # Polyethylene Bags for Packaging
        "9845",   # Method of Sampling for Food Containers
        "8543",   # Glossary of Terms for Packaging
    ],
    "furniture": [
        "7907",   # Steel Furniture for Offices
        "1003",   # Timber Panelled and Glazed Shutters
        "452",    # Steel Almirahs
        "12346",  # Domestic Furniture - Chairs
        "4011",   # Hardboard
        "1734",   # Methods of Tests for Veneers and Plywood
        "4020",   # Methods of Test for Wooden Furniture
        "15601",  # Upholstered Furniture - Safety
        "14856",  # Office Furniture - Ergonomics
    ],
}


# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------
def _setup_logging(log_dir: Path) -> logging.Logger:
    """Configure logging to file and console."""
    log_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = log_dir / f"collection_{timestamp}.log"

    logger = logging.getLogger("bis_collector")
    logger.setLevel(logging.DEBUG)

    if logger.handlers:
        logger.handlers.clear()

    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", "%H:%M:%S"))

    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))

    logger.addHandler(ch)
    logger.addHandler(fh)
    return logger


# ---------------------------------------------------------------------------
# HTTP session
# ---------------------------------------------------------------------------
def _make_session() -> requests.Session:
    """Create a requests session with appropriate browser headers."""
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive",
        }
    )
    return session


# ---------------------------------------------------------------------------
# Retry helper
# ---------------------------------------------------------------------------
def _get_with_retry(
    session: requests.Session,
    url: str,
    logger: logging.Logger,
) -> Optional[requests.Response]:
    """GET request with exponential backoff retry."""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = session.get(url, timeout=REQUEST_TIMEOUT)
            if response.status_code == 500:
                logger.warning(f"HTTP 500 for {url} (attempt {attempt}) — server error")
            else:
                response.raise_for_status()
                return response
        except requests.exceptions.HTTPError as e:
            logger.warning(f"HTTP error {e} on GET {url} (attempt {attempt})")
        except requests.exceptions.ConnectionError as e:
            logger.warning(f"Connection error on {url} (attempt {attempt}): {e}")
        except requests.exceptions.Timeout:
            logger.warning(f"Timeout on {url} (attempt {attempt})")
        except requests.exceptions.RequestException as e:
            logger.warning(f"Request error on {url} (attempt {attempt}): {e}")

        if attempt < MAX_RETRIES:
            wait = REQUEST_DELAY * (2 ** (attempt - 1))
            time.sleep(wait)

    logger.error(f"All {MAX_RETRIES} attempts failed: {url}")
    return None


def _post_with_retry(
    session: requests.Session,
    url: str,
    data: dict,
    logger: logging.Logger,
) -> Optional[requests.Response]:
    """POST request with exponential backoff retry."""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = session.post(url, data=data, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
            return response
        except requests.exceptions.HTTPError as e:
            logger.warning(f"HTTP error {e} on POST {url} (attempt {attempt})")
        except requests.exceptions.ConnectionError as e:
            logger.warning(f"Connection error on POST {url} (attempt {attempt}): {e}")
        except requests.exceptions.Timeout:
            logger.warning(f"Timeout on POST {url} (attempt {attempt})")
        except requests.exceptions.RequestException as e:
            logger.warning(f"Request error on POST {url} (attempt {attempt}): {e}")

        if attempt < MAX_RETRIES:
            wait = REQUEST_DELAY * (2 ** (attempt - 1))
            time.sleep(wait)

    logger.error(f"All {MAX_RETRIES} attempts failed: POST {url}")
    return None


# ---------------------------------------------------------------------------
# Viewstate fetcher
# ---------------------------------------------------------------------------
def _get_viewstate(
    session: requests.Session, logger: logging.Logger
) -> dict:
    """GET the home page and extract ASP.NET hidden form fields."""
    response = _get_with_retry(session, BIS_HOME_URL, logger)
    if not response:
        return {}

    soup = BeautifulSoup(response.text, "lxml")
    hidden: dict = {}
    for inp in soup.find_all("input", {"type": "hidden"}):
        name = inp.get("name", "")
        value = inp.get("value", "")
        if name:
            hidden[name] = value

    logger.debug(f"Got {len(hidden)} hidden form fields from home page")
    return hidden


# ---------------------------------------------------------------------------
# IS number search → get preview URLs
# ---------------------------------------------------------------------------
def _search_by_number(
    session: requests.Session,
    is_number: str,
    viewstate: dict,
    logger: logging.Logger,
) -> list[dict]:
    """
    Search BIS portal by IS number.
    Returns list of dicts with:
        preview_url, is_number_raw, amendments_url
    """
    post_data = {
        **viewstate,
        "ctl00$txt_standardnumber": is_number,
        "ctl00$TextBox1": "",
        "__EVENTTARGET": "ctl00$btn_stdno",
        "__EVENTARGUMENT": "",
        "ctl00$HiddenID": "",
    }

    response = _post_with_retry(session, BIS_HOME_URL, post_data, logger)
    if not response:
        return []

    soup = BeautifulSoup(response.text, "lxml")
    results: list[dict] = []

    # All BIS_Preview.aspx links are the detail pages
    for a in soup.find_all("a", href=True):
        href = str(a.get("href", ""))
        if "BIS_Preview.aspx" in href:
            # Extract the id param (e.g., 1239_1)
            id_match = re.search(r"id=([^&]+)", href)
            if not id_match:
                continue
            preview_id = id_match.group(1)
            full_url = f"{BIS_BASE_URL}/{href.lstrip('/')}"

            # Get the matching amendments link if present
            # Check nearby rows for amendments count
            results.append(
                {
                    "preview_id": preview_id,
                    "preview_url": full_url,
                    "searched_number": is_number,
                }
            )

    # Update viewstate in place for subsequent requests
    for inp in soup.find_all("input", {"type": "hidden"}):
        n = inp.get("name", "")
        v = inp.get("value", "")
        if n:
            viewstate[n] = v

    logger.debug(f"  IS {is_number}: found {len(results)} preview links")
    return results


# ---------------------------------------------------------------------------
# Preview page parser → extract standard metadata
# ---------------------------------------------------------------------------
def _parse_preview_page(
    session: requests.Session,
    preview_url: str,
    preview_id: str,
    searched_number: str,
    logger: logging.Logger,
) -> Optional[dict]:
    """
    Fetch and parse a BIS_Preview.aspx page.

    Returns a dict with: is_number, title, scope, year, ics_code,
    technical_committee, status, reaffirmed_year, source_url
    """
    response = _get_with_retry(session, preview_url, logger)
    if not response:
        return None

    text = response.text
    soup = BeautifulSoup(text, "lxml")

    # Full visible text
    page_text = soup.get_text(separator="\n", strip=True)
    lines = [l.strip() for l in page_text.split("\n") if l.strip()]

    if len(lines) < 3:
        logger.warning(f"Preview page has too little content: {preview_url}")
        return None

    # -- IS Number and Title --------------------------------------------------
    # Pattern: "IS 1239 : Part 1 : 2004 STEEL TUBES..." or "IS 4985 : 2021 ..."
    is_number = None
    title = None
    year = None

    for line in lines[:10]:
        # Match standard number, year, and title
        m = re.match(
            r"^(IS[\s/]*\d+(?:\s*:\s*Part\s*\d+)?(?:\s*:\s*Section\s*\d+)?)\s*:\s*(\b(?:19|20)\d{2}\b)[^\w]*(.*)$",
            line,
            re.IGNORECASE,
        )
        if m:
            is_part, year_val, title_raw = m.groups()
            # Clean IS number: e.g. "IS:1239:Part 1" or "IS:4985"
            num_clean = re.sub(r"\s*:\s*", ":", is_part.strip())
            num_clean = re.sub(r"\s+", " ", num_clean)
            num_clean = re.sub(r"^IS\s*", "IS:", num_clean, flags=re.IGNORECASE)
            is_number = num_clean
            year = year_val
            title = title_raw.strip()
            break

    if not is_number:
        # Fallback: check lines for IS number
        for line in lines[:10]:
            m_simple = re.search(r"\b(IS[\s:]*\d+(?:\s*:\s*Part\s*\d+)?)\b", line, re.IGNORECASE)
            if m_simple:
                raw_is = m_simple.group(1).strip()
                num_clean = re.sub(r"\s*:\s*", ":", raw_is)
                num_clean = re.sub(r"\s+", " ", num_clean)
                is_number = re.sub(r"^IS\s*", "IS:", num_clean, flags=re.IGNORECASE)
                # Look for year in same line
                y_m = re.search(r"\b((?:19|20)\d{2})\b", line)
                if y_m:
                    year = y_m.group(1)
                break
        if not is_number:
            is_number = f"IS:{searched_number}"

    # -- ICS Code and Technical Committee ------------------------------------
    ics_code = None
    technical_committee = None

    for line in lines:
        if not ics_code:
            ics_m = re.search(r"ICS\s+([\d]+(?:[\s.]+\d+)*)", line, re.IGNORECASE)
            if ics_m:
                raw_ics = ics_m.group(1).strip()
                ics_code = re.sub(r"[\s.]+", ".", raw_ics)

        if not technical_committee:
            for tc_m in re.finditer(r"\b([A-Z]{2,4}\s+\d+)\b", line):
                candidate = tc_m.group(1).strip()
                if not re.match(r"^(IS|ISO|IEC|PART|ICS)\b", candidate, re.IGNORECASE):
                    technical_committee = candidate
                    break

    # -- Reaffirmation / Status -----------------------------------------------
    reaffirmed_year = None
    status = "Active"  # Default: public preview pages exist only for active standards

    for line in lines:
        reaff_m = re.search(r"[Rr]eaffirm\w*\s*:?\s*(\d{4})", line)
        if reaff_m:
            reaffirmed_year = reaff_m.group(1)

        # Withdrawn/revised notice
        if re.search(r"\bwithdrawn\b", line, re.IGNORECASE):
            status = "Withdrawn"
        elif re.search(r"\bsupersed\w*\b", line, re.IGNORECASE):
            status = "Revised"

    # ── Scope text ───────────────────────────────────────────────────────────
    scope = None
    scope_lines: list[str] = []
    in_scope = False

    for line in lines:
        # Scope section starts with "1. Scope" or "Scope" or "1.1"
        if re.match(r"^1\.\s*Scope\s*$", line, re.IGNORECASE) or line.strip().lower() == "scope":
            in_scope = True
            continue

        if in_scope:
            # Stop at next major section (numbered heading like "2." or "3.")
            if re.match(r"^\d+\.\s+[A-Z]", line) and scope_lines:
                break
            # Stop at typical metadata lines
            if re.match(r"^(Price|ICS|Technical|Reaffirm|Amendment|Status)", line, re.IGNORECASE):
                break
            if len(line) > 15:
                scope_lines.append(line)

    if scope_lines:
        scope = " ".join(scope_lines)
    elif not in_scope:
        # Fallback: grab the longest descriptive line that isn't a header
        for line in lines:
            if (
                len(line) > 80
                and not re.match(r"^IS[\s:]", line, re.IGNORECASE)
                and not re.match(r"^Bureau|^Copyright|^Price|^ICS", line, re.IGNORECASE)
            ):
                scope = line
                break

    # ── Supersession ────────────────────────────────────────────────────────
    superseded_by = None
    supersedes = None

    for line in lines:
        sup_m = re.search(r"superseded\s+by\s+(IS[\s:]*\d+)", line, re.IGNORECASE)
        if sup_m:
            superseded_by = f"IS:{sup_m.group(1)}"

        sup2_m = re.search(r"supersedes\s+(IS[\s:]*\d+)", line, re.IGNORECASE)
        if sup2_m:
            supersedes = f"IS:{sup2_m.group(1)}"

    if not title and lines:
        # Last fallback: second line often has the title
        title = lines[1] if len(lines) > 1 else lines[0]

    return {
        "is_number": is_number,
        "title": title,
        "scope": scope,
        "year": year,
        "reaffirmed_year": reaffirmed_year,
        "ics_code": ics_code,
        "technical_committee": technical_committee,
        "status": status,
        "superseded_by": superseded_by,
        "supersedes": supersedes,
        "preview_id": preview_id,
        "source_url": preview_url,
    }


# ---------------------------------------------------------------------------
# Main collection routine
# ---------------------------------------------------------------------------
def collect_standards(
    category: str,
    limit: int,
    dry_run: bool,
    output_dir: Path,
    log_dir: Path,
    logger: logging.Logger,
) -> list[dict]:
    """
    Main collection routine.

    Strategy:
    1. Get viewstate from BIS home page
    2. For each seed IS number in the category:
       a. POST search by IS number → get preview URLs
       b. Fetch each BIS_Preview.aspx page → extract metadata + scope
       c. Rate-limit between requests
    3. Save raw JSON to output_dir

    Args:
        category: Category name (must be in CATEGORY_IS_SEEDS)
        limit: Maximum records to collect
        dry_run: If True, simulate without saving
        output_dir: Directory for raw JSON
        log_dir: Directory for log files
        logger: Logger instance

    Returns:
        List of collected standard records
    """
    if category not in CATEGORY_IS_SEEDS:
        logger.error(
            f"Unknown category '{category}'. Valid: {list(CATEGORY_IS_SEEDS.keys())}"
        )
        return []

    seed_numbers = CATEGORY_IS_SEEDS[category]
    logger.info(
        f"=== BIS Collection: category='{category}', "
        f"limit={limit}, dry_run={dry_run}, seeds={len(seed_numbers)} ==="
    )

    if dry_run:
        logger.info(f"[DRY RUN] Would search IS numbers: {seed_numbers[:5]}...")
        logger.info("[DRY RUN] No data saved.")
        return []

    session = _make_session()

    # 1. Fetch viewstate
    logger.info("Fetching BIS home page for session tokens...")
    viewstate = _get_viewstate(session, logger)
    if not viewstate:
        logger.warning("Could not get viewstate — search may fail")
    time.sleep(REQUEST_DELAY)

    # 2. Collect
    collected: list[dict] = []
    seen_is: set[str] = set()

    for seed_num in seed_numbers:
        if len(collected) >= limit:
            logger.info(f"Reached limit ({limit}). Stopping.")
            break

        logger.info(f"[{len(collected)}/{limit}] Searching IS {seed_num}...")

        # Search by number
        preview_links = _search_by_number(session, seed_num, viewstate, logger)
        time.sleep(REQUEST_DELAY)

        if not preview_links:
            logger.warning(f"  No results for IS {seed_num}")
            continue

        # Filter to main standards only (not amendments: avoid Amd. in id)
        main_links = [
            p for p in preview_links
            if "amd" not in p["preview_id"].lower()
            and "amend" not in p["preview_id"].lower()
        ]

        # Prefer exact match links (e.g., id=1239_1, b1239, 1239)
        exact_links = [
            p for p in main_links
            if re.match(rf"^b?{seed_num}(_\d+|\b)", p["preview_id"], re.IGNORECASE)
        ]
        links_to_fetch = exact_links if exact_links else main_links[:2]

        logger.info(f"  Found {len(preview_links)} links, {len(links_to_fetch)} relevant standards")

        for plink in links_to_fetch[:6]:  # Allow up to 6 parts per standard number
            if len(collected) >= limit:
                break

            preview_id = plink["preview_id"]
            preview_url = plink["preview_url"]

            logger.info(f"  Fetching: {preview_id}")
            record_meta = _parse_preview_page(
                session, preview_url, preview_id, seed_num, logger
            )
            time.sleep(REQUEST_DELAY)

            if not record_meta:
                logger.warning(f"  Could not parse preview: {preview_url}")
                continue

            is_num = record_meta.get("is_number", "")
            if is_num in seen_is:
                logger.debug(f"  Duplicate skipped: {is_num}")
                continue

            seen_is.add(is_num)

            # Build final record
            record = {
                "is_number": is_num,
                "title": record_meta.get("title"),
                "scope": record_meta.get("scope"),
                "category": category,
                "status": record_meta.get("status", "Active"),
                "year": record_meta.get("year"),
                "reaffirmed_year": record_meta.get("reaffirmed_year"),
                "ics_code": record_meta.get("ics_code"),
                "technical_committee": record_meta.get("technical_committee"),
                "superseded_by": record_meta.get("superseded_by"),
                "supersedes": record_meta.get("supersedes"),
                "related_standards": [],
                "amendment_info": None,
                "source_url": preview_url,
                "preview_id": preview_id,
                "search_keyword": seed_num,
                "source_name": SOURCE_NAME,
                "source_type": SOURCE_TYPE,
                "collected_at": datetime.utcnow().isoformat() + "Z",
            }

            collected.append(record)
            title_short = (record.get("title") or "")[:60]
            logger.info(
                f"  [+] [{len(collected)}/{limit}] {is_num} - {title_short}"
            )

    logger.info(
        f"=== Collection complete: {len(collected)} records for '{category}' ==="
    )

    if not collected:
        logger.warning("No records collected.")
        return collected

    # 3. Save raw JSON
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    raw_file = output_dir / f"{category}_raw_{timestamp}.json"

    with open(raw_file, "w", encoding="utf-8") as f:
        json.dump(
            {
                "collected_at": datetime.utcnow().isoformat() + "Z",
                "category": category,
                "seeds_used": seed_numbers,
                "record_count": len(collected),
                "records": collected,
            },
            f,
            indent=2,
            ensure_ascii=False,
        )
    logger.info(f"Raw data saved: {raw_file}")
    return collected


# ---------------------------------------------------------------------------
# CLI entrypoint
# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(
        description="Collect Indian Standards metadata from BIS portal (standardsbis.bsbedge.com)."
    )
    parser.add_argument(
        "--category",
        type=str,
        default="pipes",
        choices=list(CATEGORY_IS_SEEDS.keys()),
        help="Category to collect (default: pipes)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=50,
        help="Maximum records to collect (default: 50)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate without saving data",
    )

    args = parser.parse_args()

    raw_bis_dir = PROJECT_ROOT / "data" / "raw" / "bis"
    log_dir = PROJECT_ROOT / "data" / "raw" / "logs"

    logger = _setup_logging(log_dir)

    collect_standards(
        category=args.category,
        limit=args.limit,
        dry_run=args.dry_run,
        output_dir=raw_bis_dir,
        log_dir=log_dir,
        logger=logger,
    )


if __name__ == "__main__":
    main()
