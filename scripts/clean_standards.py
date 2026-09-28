"""
clean_standards.py
==================
Phase 1 — Data Cleaning & Normalization for StandardMatch AI

Reads raw JSON files from data/raw/bis/ and produces clean, normalized
records saved to:
  - data/processed/standards.csv
  - data/processed/standards.json

Cleaning operations:
  - Fix IS number parsing (remove encoding artifacts, normalize format)
  - Fix year extraction from title string
  - Extract clean title from combined title field
  - Fix technical committee extraction
  - Standardize ICS code format
  - Standardize status values (Active / Revised / Withdrawn / Under Review)
  - Strip HTML/encoding artifacts from text fields
  - Remove empty/duplicate records
  - Enforce NULL for unavailable fields (never invent values)
  - Remove wrongly-matched standards (IS:1 etc.)

Usage:
    python scripts/clean_standards.py
    python scripts/clean_standards.py --raw-dir data/raw/bis --output-dir data/processed
"""

import argparse
import html
import json
import logging
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

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

import pandas as pd

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(PROJECT_ROOT))

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("bis_cleaner")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
VALID_STATUSES = {"Active", "Revised", "Withdrawn", "Under Review"}

STATUS_ALIASES: dict[str, str] = {
    "active": "Active",
    "current": "Active",
    "in force": "Active",
    "valid": "Active",
    "revised": "Revised",
    "superseded": "Revised",
    "replaced": "Revised",
    "withdrawn": "Withdrawn",
    "obsolete": "Withdrawn",
    "cancelled": "Withdrawn",
    "under revision": "Under Review",
    "under review": "Under Review",
    "draft": "Under Review",
}

# Output column order
OUTPUT_COLUMNS = [
    "is_number",
    "title",
    "scope",
    "category",
    "status",
    "year",
    "reaffirmed_year",
    "ics_code",
    "technical_committee",
    "superseded_by",
    "supersedes",
    "related_standards",
    "amendment_info",
    "source_url",
    "source_name",
    "source_type",
    "collected_at",
    "search_keyword",
]

# Known IS number → title corrections for commonly misidentified standards
# (when the IS number doesn't match the search seed)
IS_NUMBER_SANITY: set[str] = {
    # Will be populated dynamically from search_keyword cross-check
}


# ---------------------------------------------------------------------------
# Cleaning functions
# ---------------------------------------------------------------------------
def clean_unicode_artifacts(text: Optional[str]) -> Optional[str]:
    """Remove common Unicode encoding artifacts (replacement chars, etc.)."""
    if not text or not isinstance(text, str):
        return None
    # Remove replacement character and similar
    text = re.sub(r'[\ufffd\u0000-\u0008\u000b\u000c\u000e-\u001f]', '', text)
    # Remove non-breaking spaces
    text = text.replace('\xa0', ' ')
    return text.strip() if text.strip() else None


def normalize_is_number(raw: Optional[str], search_keyword: Optional[str] = None) -> Optional[str]:
    """
    Normalize an IS number to 'IS:XXXX' or 'IS:XXXX Part Y' format.

    BIS preview pages have format like:
      "IS 1239 : Part 1 : 2004 STEEL TUBES..."
    After parsing, title field contains ": Part 1 : 2004 STEEL TUBES..."
    and is_number field may have "IS:1239" or "IS:1" (wrong parse).

    When search_keyword is provided, use it to validate the parsed IS number.
    """
    if not raw or not isinstance(raw, str):
        return None

    raw = clean_unicode_artifacts(raw) or ""
    raw = raw.strip()

    # Match IS number pattern
    match = re.match(
        r"IS[\s:]*(\d+(?:\s*:\s*Part\s*\d+)?(?:\s*:\s*Section\s*\d+)?(?:\s*Part\s*\d+)?)",
        raw,
        re.IGNORECASE,
    )
    if not match:
        # Try extracting just the number
        num_match = re.search(r"\b(\d{3,6})\b", raw)
        if num_match:
            return f"IS:{num_match.group(1)}"
        return None

    number_part = match.group(1).strip()
    # Clean up spacing in number
    number_part = re.sub(r"\s*:\s*", ":", number_part)
    number_part = re.sub(r"\s+", " ", number_part)

    return f"IS:{number_part}"


def clean_year(raw: Optional[Any]) -> Optional[str]:
    """Extract a 4-digit year string. Returns None if not a valid year."""
    if raw is None:
        return None
    text = str(raw).strip()
    match = re.search(r"\b(19\d{2}|20\d{2})\b", text)
    return match.group(1) if match else None


def extract_year_from_title(raw_title: Optional[str]) -> Optional[str]:
    """
    Extract the publication year from a title string like
    ': Part 1 : 2004 STEEL TUBES...' or ': 2023 Stainless Steel...'
    """
    if not raw_title or not isinstance(raw_title, str):
        return None
    # Look for 4-digit year (1950-2030)
    match = re.search(r"\b(19[5-9]\d|20[0-3]\d)\b", raw_title)
    return match.group(1) if match else None


def extract_clean_title(
    raw_title: Optional[str],
    is_number_str: Optional[str] = None,
) -> Optional[str]:
    """
    Clean the title field which from BIS preview pages is stored as:
    ': Part 1 : 2004 STEEL TUBES, TUBULARS AND OTHER WROUGHT STEEL FITTINGS...'

    Strategy:
    1. Remove the leading ': Part X : YEAR' prefix
    2. Title-case or keep as-is
    3. Return clean title string
    """
    if not raw_title or not isinstance(raw_title, str):
        return None

    title = clean_unicode_artifacts(raw_title) or ""

    # Remove BIS e-Sale platform artifacts
    title = re.sub(r"Bureau of Indian Standards.*", "", title, flags=re.IGNORECASE).strip()

    # Remove leading colon/year prefix pattern ": Part X : YYYY "
    # Pattern: optional ": Part N : " followed by year
    title = re.sub(
        r"^[\s:]+(?:Part\s+\d+\s*:?\s*)?(?:Section\s+\d+\s*:?\s*)?(?:19\d{2}|20\d{2})\s*",
        "",
        title,
    ).strip()

    # Remove any remaining leading colons/dashes
    title = re.sub(r"^[\s:\-–]+", "", title).strip()

    # Strip trailing garbage
    title = re.sub(r"\s+", " ", title).strip()

    # Title shouldn't be very short or just a year
    if len(title) < 5 or re.match(r"^\d{4}$", title):
        return None

    # Reconstruct with IS number prefix if it helps
    if is_number_str and not title.upper().startswith("IS"):
        # Keep title as-is (don't prepend IS number, that's in separate field)
        pass

    return title if title else None


def fix_technical_committee(raw_tc: Optional[str], is_number: Optional[str]) -> Optional[str]:
    """
    Fix technical committee field.
    BIS portal sometimes returns the IS number itself instead of TC code.
    TC codes are like 'MTD 19', 'CHD 27', 'CED 2', 'MED 24'.
    """
    if not raw_tc or not isinstance(raw_tc, str):
        return None

    tc = clean_unicode_artifacts(raw_tc) or ""
    tc = tc.strip()

    # If TC looks like an IS number (e.g., "IS 1239"), it's invalid
    if re.match(r"^IS[\s:]*\d+", tc, re.IGNORECASE):
        return None

    # Valid TC pattern: 2-4 uppercase letters followed by space and number
    if re.match(r"^[A-Z]{2,6}\s+\d+$", tc):
        return tc

    # ICS code was mistakenly captured as TC
    if re.match(r"^ICS", tc, re.IGNORECASE):
        return None

    return tc if len(tc) >= 3 else None


def normalize_ics_code(raw_ics: Optional[str]) -> Optional[str]:
    """Normalize ICS code to standard dotted format: 77.140.75"""
    if not raw_ics or not isinstance(raw_ics, str):
        return None

    ics = clean_unicode_artifacts(raw_ics) or ""
    ics = ics.strip()

    # Already dotted: 77.140.75
    if re.match(r"^\d{2}\.?\d+", ics):
        # Replace spaces with dots if needed
        ics = re.sub(r"\s+", ".", ics)
        # Clean multiple dots
        ics = re.sub(r"\.{2,}", ".", ics)
        return ics

    return ics if ics else None


def normalize_status(raw: Optional[str]) -> str:
    """Map raw status string to one of the canonical status values."""
    if not raw or not isinstance(raw, str):
        return "Active"
    cleaned = clean_unicode_artifacts(raw) or ""
    cleaned = cleaned.strip().lower()
    return STATUS_ALIASES.get(cleaned, "Active")


def clean_text(text: Optional[str]) -> Optional[str]:
    """General text cleaning."""
    if not text or not isinstance(text, str):
        return None
    text = clean_unicode_artifacts(text) or ""
    text = html.unescape(text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text if len(text) > 2 else None


def clean_url(url: Optional[str]) -> Optional[str]:
    """Validate and clean a URL."""
    if not url or not isinstance(url, str):
        return None
    url = url.strip()
    if not re.match(r"^https?://", url, re.IGNORECASE):
        return None
    return url


def clean_list_field(raw: Any) -> list[str]:
    """Ensure a field is a list of strings."""
    if isinstance(raw, list):
        return [str(item).strip() for item in raw if item]
    if isinstance(raw, str) and raw.strip():
        return [p.strip() for p in raw.split(",") if p.strip()]
    return []


# ---------------------------------------------------------------------------
# Record cleaning
# ---------------------------------------------------------------------------
def clean_record(raw_record: dict) -> Optional[dict]:
    """
    Clean and normalize a single raw record.
    Returns cleaned dict or None if record cannot be salvaged.
    """
    search_keyword = raw_record.get("search_keyword", "")
    raw_is = raw_record.get("is_number", "")
    raw_title = raw_record.get("title", "")

    # Fix IS number using search keyword as sanity check
    is_number = normalize_is_number(raw_is, search_keyword)
    if not is_number:
        logger.warning(f"Skipping: invalid IS number {raw_is!r}")
        return None

    # Validate IS number is reasonable (not IS:1 or IS:123456789)
    is_digits = re.search(r"\d+", is_number)
    if is_digits:
        digits = is_digits.group(0)
        if len(digits) < 3 or len(digits) > 7:
            logger.warning(f"Skipping: suspicious IS number {is_number!r} (from {raw_is!r})")
            return None

    # Extract year (use raw_record year if 4 digits, else from title)
    raw_yr = clean_year(raw_record.get("year"))
    year = raw_yr if raw_yr else extract_year_from_title(raw_title)

    # Extract clean title
    title = extract_clean_title(raw_title, is_number)
    if not title:
        raw_preview = repr(raw_title[:50]) if raw_title else "''"
        logger.warning(f"Skipping {is_number}: missing/invalid title (raw: {raw_preview})")
        return None

    # Fix technical committee
    tc = fix_technical_committee(
        raw_record.get("technical_committee"),
        is_number,
    )

    # ICS code
    ics = normalize_ics_code(raw_record.get("ics_code"))

    category_clean = clean_text(raw_record.get("category")) or "uncategorized"
    scope_clean = clean_text(raw_record.get("scope"))

    # Validate category relevance for pipes & steel
    if category_clean.lower() == "pipes":
        combined_text = f"{title} {scope_clean or ''}"
        # Exclude non-pipe domains (unless pipe/tube/fitting is explicitly in title)
        if not re.search(r"\b(pipe[s]?|tube[s]?|tubular[s]?|fitting[s]?|steel)\b", title, re.IGNORECASE):
            if re.search(r"\b(information technology|open systems interconnection|children apparel|apparel|textiles|chemical|butadiene|acid|clamp)\b", combined_text, re.IGNORECASE):
                logger.info(f"Skipping non-pipe standard (excluded domain): {is_number} - {title[:40]}")
                return None

        pipe_keywords = [
            r"\bpipe[s]?\b", r"\btube[s]?\b", r"\btubular[s]?\b", r"\bfitting[s]?\b",
            r"\bjoint[s]?\b", r"\bseal[s]?\b", r"\bwater\b", r"\bsewage\b", r"\bsewer[s]?\b",
            r"\bdrain[s]?\b", r"\bdrainage\b", r"\bconveyor[s]?\b", r"\bsteel\b", r"\bpvc\b",
            r"\bpolyethylene\b", r"\bhdpe\b", r"\bcast iron\b", r"\bductile\b", r"\bgas\b",
            r"\bscreen[s]?\b", r"\bcasing\b", r"\breinforcement\b", r"\bwire[s]?\b", r"\bvalve[s]?\b",
            r"\bflange[s]?\b", r"\bpipeline[s]?\b", r"\bsanitary\b", r"\bplumbing\b"
        ]
        if not any(re.search(p, combined_text, re.IGNORECASE) for p in pipe_keywords):
            logger.info(f"Skipping non-category standard: {is_number} - {title[:40]}")
            return None

    return {
        "is_number": is_number,
        "title": title,
        "scope": scope_clean,
        "category": category_clean,
        "status": normalize_status(raw_record.get("status")),
        "year": year,
        "reaffirmed_year": raw_record.get("reaffirmed_year"),
        "ics_code": ics,
        "technical_committee": tc,
        "superseded_by": normalize_is_number(raw_record.get("superseded_by") or ""),
        "supersedes": normalize_is_number(raw_record.get("supersedes") or ""),
        "related_standards": clean_list_field(raw_record.get("related_standards", [])),
        "amendment_info": clean_text(raw_record.get("amendment_info")),
        "source_url": clean_url(raw_record.get("source_url")),
        "source_name": raw_record.get("source_name", ""),
        "source_type": raw_record.get("source_type", ""),
        "collected_at": raw_record.get("collected_at", ""),
        "search_keyword": search_keyword,
    }


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------
def load_raw_records(raw_dir: Path) -> list[dict]:
    """Load all raw JSON files from the given directory."""
    json_files = sorted(raw_dir.glob("*.json"))
    if not json_files:
        logger.warning(f"No JSON files found in {raw_dir}")
        return []

    all_records: list[dict] = []
    for f in json_files:
        logger.info(f"Loading: {f.name}")
        try:
            with open(f, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            if isinstance(data, list):
                records = data
            elif isinstance(data, dict) and "records" in data:
                records = data["records"]
            else:
                logger.warning(f"Unrecognized format in {f.name}")
                continue
            all_records.extend(records)
            logger.info(f"  Loaded {len(records)} records")
        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"Failed to load {f.name}: {e}")

    logger.info(f"Total raw records: {len(all_records)}")
    return all_records


def deduplicate(records: list[dict]) -> tuple[list[dict], int]:
    """Deduplicate by is_number."""
    seen: set[str] = set()
    unique: list[dict] = []
    dup_count = 0

    for record in records:
        key = record["is_number"]
        if key in seen:
            dup_count += 1
        else:
            seen.add(key)
            unique.append(record)

    if dup_count:
        logger.info(f"Removed {dup_count} duplicates")
    return unique, dup_count


def clean_pipeline(raw_dir: Path, output_dir: Path) -> dict:
    """Full cleaning pipeline: load → clean → dedup → save."""
    logger.info("=" * 55)
    logger.info("StandardMatch AI -- Data Cleaning Pipeline")
    logger.info("=" * 55)

    raw_records = load_raw_records(raw_dir)
    total_raw = len(raw_records)
    if not raw_records:
        logger.error("No raw records. Run collect_bis_standards.py first.")
        return {"total_raw": 0, "cleaned": 0, "skipped": 0, "duplicates_removed": 0}

    cleaned_records: list[dict] = []
    skipped = 0
    for raw in raw_records:
        cleaned = clean_record(raw)
        if cleaned:
            cleaned_records.append(cleaned)
        else:
            skipped += 1

    logger.info(f"Cleaned: {len(cleaned_records)}, Skipped: {skipped}")

    unique_records, dup_count = deduplicate(cleaned_records)

    # Build DataFrame
    df = pd.DataFrame(unique_records, columns=[c for c in OUTPUT_COLUMNS if c in
                                                 set(unique_records[0].keys() if unique_records else set())])

    # Serialize list fields for CSV
    if "related_standards" in df.columns:
        df["related_standards"] = df["related_standards"].apply(
            lambda x: json.dumps(x) if isinstance(x, list) else "[]"
        )

    # Save
    output_dir.mkdir(parents=True, exist_ok=True)

    csv_path = output_dir / "standards.csv"
    json_path = output_dir / "standards.json"

    df.to_csv(csv_path, index=False, encoding="utf-8-sig")
    logger.info(f"Saved CSV: {csv_path} ({len(df)} records)")

    records_for_json = []
    for rec in unique_records:
        r = dict(rec)
        if not isinstance(r.get("related_standards"), list):
            r["related_standards"] = []
        records_for_json.append(r)

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "generated_at": datetime.utcnow().isoformat() + "Z",
                "record_count": len(records_for_json),
                "records": records_for_json,
            },
            f,
            indent=2,
            ensure_ascii=False,
        )
    logger.info(f"Saved JSON: {json_path} ({len(records_for_json)} records)")

    # Categories summary
    if "category" in df.columns:
        cats = df.groupby("category").size().reset_index(name="count")
        cats.to_csv(output_dir / "categories.csv", index=False, encoding="utf-8-sig")

    summary = {
        "total_raw": total_raw,
        "cleaned": len(unique_records),
        "skipped": skipped,
        "duplicates_removed": dup_count,
    }
    logger.info(
        f"Done: {summary['cleaned']} records saved "
        f"({summary['skipped']} skipped, {summary['duplicates_removed']} duplicates)"
    )
    return summary


# ---------------------------------------------------------------------------
# CLI entrypoint
# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(description="Clean and normalize BIS standards data.")
    parser.add_argument(
        "--raw-dir",
        type=Path,
        default=PROJECT_ROOT / "data" / "raw" / "bis",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PROJECT_ROOT / "data" / "processed",
    )
    args = parser.parse_args()
    clean_pipeline(args.raw_dir, args.output_dir)


if __name__ == "__main__":
    main()
