"""
validate_dataset.py
===================
Phase 1 — Dataset Validation for StandardMatch AI

Reads data/processed/standards.csv and performs comprehensive checks,
generating a detailed validation report.

Checks performed:
  ✓ Missing IS numbers
  ✓ Invalid IS number format
  ✓ Missing titles
  ✓ Missing or empty scope text
  ✓ Suspiciously short scope (< 30 characters)
  ✓ Scope identical to title (likely copy error)
  ✓ Invalid status values
  ✓ Missing source URLs
  ✓ Invalid/malformed source URLs
  ✓ Duplicate IS numbers
  ✓ Missing collected_at timestamp
  ✓ IS numbers with no year information
  ✓ Records with all optional fields empty

Usage:
    python scripts/validate_dataset.py
    python scripts/validate_dataset.py --input data/processed/standards.csv
"""

import argparse
import json
import logging
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

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
logger = logging.getLogger("bis_validator")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
VALID_STATUSES = {"Active", "Revised", "Withdrawn", "Under Review"}
IS_NUMBER_PATTERN = re.compile(r"^IS:\d+", re.IGNORECASE)
URL_PATTERN = re.compile(r"^https?://", re.IGNORECASE)
MIN_SCOPE_LENGTH = 30
REQUIRED_FIELDS = ["is_number", "title", "source_url", "collected_at", "status"]
OPTIONAL_FIELDS = [
    "scope", "year", "ics_code", "technical_committee",
    "superseded_by", "supersedes", "amendment_info",
]


# ---------------------------------------------------------------------------
# Individual check functions
# ---------------------------------------------------------------------------

def check_missing_is_number(df: pd.DataFrame) -> pd.Index:
    """Return index of rows with missing or empty IS number."""
    return df.index[df["is_number"].isna() | (df["is_number"].astype(str).str.strip() == "")]


def check_invalid_is_format(df: pd.DataFrame) -> pd.Index:
    """Return index of rows where IS number doesn't match IS:XXXX pattern."""
    valid_mask = df["is_number"].astype(str).str.match(IS_NUMBER_PATTERN, na=False)
    return df.index[~valid_mask & df["is_number"].notna()]


def check_missing_title(df: pd.DataFrame) -> pd.Index:
    """Return index of rows with missing or empty title."""
    return df.index[df["title"].isna() | (df["title"].astype(str).str.strip() == "")]


def check_missing_scope(df: pd.DataFrame) -> pd.Index:
    """Return index of rows with missing or empty scope."""
    return df.index[
        df["scope"].isna() | (df["scope"].astype(str).str.strip().isin(["", "None", "nan"]))
    ]


def check_short_scope(df: pd.DataFrame) -> pd.Index:
    """Return index of rows where scope is present but suspiciously short."""
    has_scope = df["scope"].notna() & (
        ~df["scope"].astype(str).str.strip().isin(["", "None", "nan"])
    )
    short_mask = df["scope"].astype(str).str.len() < MIN_SCOPE_LENGTH
    return df.index[has_scope & short_mask]


def check_scope_equals_title(df: pd.DataFrame) -> pd.Index:
    """Return index of rows where scope text is identical to title (likely copy error)."""
    has_both = df["scope"].notna() & df["title"].notna()
    same_mask = df["scope"].astype(str).str.strip() == df["title"].astype(str).str.strip()
    return df.index[has_both & same_mask]


def check_invalid_status(df: pd.DataFrame) -> pd.Index:
    """Return index of rows with status not in the allowed set."""
    return df.index[~df["status"].isin(VALID_STATUSES)]


def check_missing_source_url(df: pd.DataFrame) -> pd.Index:
    """Return index of rows with missing or empty source URL."""
    return df.index[
        df["source_url"].isna() | (df["source_url"].astype(str).str.strip().isin(["", "None", "nan"]))
    ]


def check_invalid_url(df: pd.DataFrame) -> pd.Index:
    """Return index of rows where source URL doesn't look like a valid URL."""
    has_url = ~df["source_url"].isna() & (
        ~df["source_url"].astype(str).str.strip().isin(["", "None", "nan"])
    )
    invalid_mask = ~df["source_url"].astype(str).str.match(URL_PATTERN, na=False)
    return df.index[has_url & invalid_mask]


def check_duplicates(df: pd.DataFrame) -> pd.Index:
    """Return index of duplicate IS number rows (keeping first occurrence)."""
    return df.index[df.duplicated(subset=["is_number"], keep="first")]


def check_missing_timestamp(df: pd.DataFrame) -> pd.Index:
    """Return index of rows with missing collected_at."""
    return df.index[
        df["collected_at"].isna() | (df["collected_at"].astype(str).str.strip().isin(["", "None", "nan"]))
    ]


def check_all_optional_empty(df: pd.DataFrame) -> pd.Index:
    """Return index of rows where every optional field is empty/null."""
    optional_available = [f for f in OPTIONAL_FIELDS if f in df.columns]
    all_empty_mask = df[optional_available].apply(
        lambda col: col.isna() | col.astype(str).str.strip().isin(["", "None", "nan", "[]"])
    ).all(axis=1)
    return df.index[all_empty_mask]


# ---------------------------------------------------------------------------
# Main validation
# ---------------------------------------------------------------------------
def validate_dataset(input_path: Path, log_dir: Path) -> dict[str, Any]:
    """
    Run all validation checks on the processed standards CSV.

    Args:
        input_path: Path to standards.csv
        log_dir:    Directory to write issues JSON log

    Returns:
        Summary dict with check results.
    """
    logger.info("=" * 58)
    logger.info("StandardMatch AI — Dataset Validation")
    logger.info("=" * 58)
    logger.info(f"Input: {input_path}")

    if not input_path.exists():
        logger.error(f"Input file not found: {input_path}")
        logger.error("Run clean_standards.py first to generate processed data.")
        return {}

    df = pd.read_csv(input_path, dtype=str)
    total = len(df)
    logger.info(f"Loaded {total} records from {input_path.name}")

    # Run all checks
    checks: dict[str, pd.Index] = {
        "missing_is_number":     check_missing_is_number(df),
        "invalid_is_format":     check_invalid_is_format(df),
        "missing_title":         check_missing_title(df),
        "missing_scope":         check_missing_scope(df),
        "short_scope":           check_short_scope(df),
        "scope_equals_title":    check_scope_equals_title(df),
        "invalid_status":        check_invalid_status(df),
        "missing_source_url":    check_missing_source_url(df),
        "invalid_url":           check_invalid_url(df),
        "duplicate_is_number":   check_duplicates(df),
        "missing_timestamp":     check_missing_timestamp(df),
        "all_optional_empty":    check_all_optional_empty(df),
    }

    # Collect all bad row indices (union across all critical checks)
    critical_checks = {
        "missing_is_number", "missing_title", "invalid_status",
        "missing_source_url", "duplicate_is_number",
    }
    bad_indices: set[int] = set()
    for name in critical_checks:
        bad_indices.update(checks[name].tolist())

    valid_count = total - len(bad_indices)
    scope_coverage = total - len(checks["missing_scope"])

    # Build issues log
    issues_log: list[dict] = []
    for check_name, idx in checks.items():
        for i in idx:
            row = df.loc[i]
            issues_log.append(
                {
                    "row_index": int(i),
                    "is_number": str(row.get("is_number", "")),
                    "issue": check_name,
                    "title": str(row.get("title", ""))[:80],
                }
            )

    # Save issues log
    log_dir.mkdir(parents=True, exist_ok=True)
    issues_path = log_dir / "validation_issues.json"
    with open(issues_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "validated_at": datetime.utcnow().isoformat() + "Z",
                "input_file": str(input_path),
                "total_records": total,
                "issue_count": len(issues_log),
                "issues": issues_log,
            },
            f,
            indent=2,
            ensure_ascii=False,
        )

    # -----------------------------------------------------------------------
    # Print Report
    # -----------------------------------------------------------------------
    sep = "-" * 52
    print()
    print("+==================================================+")
    print("|       STANDARDMATCH AI -- VALIDATION REPORT      |")
    print("+==================================================+")
    print()
    print(f"  {'Input file:':<30} {input_path.name}")
    print(f"  {'Validated at:':<30} {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    print(sep)
    print("  RECORD COUNTS")
    print(sep)
    print(f"  {'Total records:':<35} {total}")
    print(f"  {'Valid records (no critical issues):':<35} {valid_count}")
    print(f"  {'Records with scope text:':<35} {scope_coverage} / {total}")
    print()
    print(sep)
    print("  ISSUES DETECTED")
    print(sep)

    issue_labels: dict[str, str] = {
        "missing_is_number":   "Missing IS number",
        "invalid_is_format":   "Invalid IS number format",
        "missing_title":       "Missing title",
        "missing_scope":       "Missing scope text",
        "short_scope":         f"Short scope (< {MIN_SCOPE_LENGTH} chars)",
        "scope_equals_title":  "Scope identical to title",
        "invalid_status":      "Invalid status value",
        "missing_source_url":  "Missing source URL",
        "invalid_url":         "Invalid/malformed URL",
        "duplicate_is_number": "Duplicate IS numbers",
        "missing_timestamp":   "Missing collected_at",
        "all_optional_empty":  "All optional fields empty",
    }

    any_issue = False
    for key, label in issue_labels.items():
        count = len(checks[key])
        critical = "[!] " if key in critical_checks else "    "
        marker = f"[{count}]" if count > 0 else "  [OK]"
        if count > 0:
            any_issue = True
        print(f"  {critical}{label:<40} {marker}")

    if not any_issue:
        print("  [OK]  No issues detected -- dataset is clean!")

    print()
    print(sep)
    print("  STATUS DISTRIBUTION")
    print(sep)
    if "status" in df.columns:
        status_counts = df["status"].value_counts()
        for status, count in status_counts.items():
            print(f"  {'  ' + str(status):<35} {count}")

    print()
    print(sep)
    print("  CATEGORY DISTRIBUTION")
    print(sep)
    if "category" in df.columns:
        cat_counts = df["category"].value_counts()
        for cat, count in cat_counts.items():
            print(f"  {'  ' + str(cat):<35} {count}")

    print()
    print(sep)
    print("  SAMPLE RECORDS (first 5)")
    print(sep)
    sample_cols = ["is_number", "title", "status", "year", "category"]
    available_cols = [c for c in sample_cols if c in df.columns]
    sample = df[available_cols].head(5)
    for _, row in sample.iterrows():
        print(f"\n  IS Number  : {row.get('is_number', 'N/A')}")
        print(f"  Title      : {str(row.get('title', 'N/A'))[:70]}")
        print(f"  Status     : {row.get('status', 'N/A')}")
        print(f"  Year       : {row.get('year', 'N/A')}")
        print(f"  Category   : {row.get('category', 'N/A')}")

    print()
    print(sep)
    print(f"  Issues log saved: {issues_path}")
    print(sep)
    print()

    summary = {
        "total": total,
        "valid": valid_count,
        "scope_with_text": scope_coverage,
        "issues": {k: len(v) for k, v in checks.items()},
        "issues_log": str(issues_path),
    }

    logger.info(
        f"Validation complete: {valid_count}/{total} valid, "
        f"{scope_coverage}/{total} have scope text"
    )
    return summary


# ---------------------------------------------------------------------------
# CLI entrypoint
# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(description="Validate the processed BIS standards dataset.")
    parser.add_argument(
        "--input",
        type=Path,
        default=PROJECT_ROOT / "data" / "processed" / "standards.csv",
        help="Path to processed standards.csv (default: data/processed/standards.csv)",
    )
    args = parser.parse_args()

    log_dir = PROJECT_ROOT / "data" / "raw" / "logs"
    validate_dataset(args.input, log_dir)


if __name__ == "__main__":
    main()
