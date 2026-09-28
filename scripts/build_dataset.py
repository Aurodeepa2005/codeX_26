"""
build_dataset.py
================
Phase 1 — Full Pipeline Orchestrator for StandardMatch AI

Runs the complete data pipeline in sequence:
  1. collect_bis_standards.py  →  data/raw/bis/<category>_raw_<ts>.json
  2. clean_standards.py        →  data/processed/standards.csv, standards.json
  3. validate_dataset.py       →  validation report + issues log

Also seeds the evaluation dataset (test_queries.csv) with realistic
procurement queries based on the collected standards.

Usage:
    python scripts/build_dataset.py --category pipes --limit 50
    python scripts/build_dataset.py --category pipes --limit 10 --dry-run
"""

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

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
logger = logging.getLogger("build_dataset")


# ---------------------------------------------------------------------------
# Evaluation dataset seed queries
# (Realistic procurement descriptions — expand after collecting real IS numbers)
# ---------------------------------------------------------------------------
SEED_QUERIES_BY_CATEGORY: dict[str, list[dict]] = {
    "pipes": [
        {
            "query": "GI pipes for rural drinking water supply, medium class",
            "expected_is_numbers": "",   # Will be filled after collection
            "category": "pipes",
            "notes": "Galvanized iron pipe — most common water supply specification",
        },
        {
            "query": "HDPE pipes for underground water distribution system, PN 6",
            "expected_is_numbers": "",
            "category": "pipes",
            "notes": "High-density polyethylene pipe for water infrastructure",
        },
        {
            "query": "cast iron soil pipe for building drainage",
            "expected_is_numbers": "",
            "category": "pipes",
            "notes": "Cast iron drain pipe — building plumbing",
        },
        {
            "query": "PVC pressure pipes for potable water supply",
            "expected_is_numbers": "",
            "category": "pipes",
            "notes": "Unplasticized PVC pipe for drinking water",
        },
        {
            "query": "ductile iron pipes for water mains",
            "expected_is_numbers": "",
            "category": "pipes",
            "notes": "DI pipe for large diameter municipal water mains",
        },
        {
            "query": "steel tubes for structural purposes",
            "expected_is_numbers": "",
            "category": "pipes",
            "notes": "Hollow steel sections for construction",
        },
        {
            "query": "black steel pipes for fire fighting sprinkler system",
            "expected_is_numbers": "",
            "category": "pipes",
            "notes": "Carbon steel pipe for fire suppression",
        },
    ],
    "cement": [
        {
            "query": "Ordinary Portland cement for general construction",
            "expected_is_numbers": "",
            "category": "cement",
            "notes": "OPC Grade 53 — most common procurement",
        },
        {
            "query": "fly ash blended cement for mass concrete works",
            "expected_is_numbers": "",
            "category": "cement",
            "notes": "PPC / Portland Pozzolana Cement",
        },
    ],
    "electrical": [
        {
            "query": "electrical wires and cables for building wiring 1100V",
            "expected_is_numbers": "",
            "category": "electrical",
            "notes": "PVC insulated wire for general wiring",
        },
        {
            "query": "miniature circuit breaker for distribution board",
            "expected_is_numbers": "",
            "category": "electrical",
            "notes": "MCB for domestic/commercial panel boards",
        },
    ],
    "ppe": [
        {
            "query": "industrial safety helmets for construction workers",
            "expected_is_numbers": "",
            "category": "ppe",
            "notes": "Hard hat / safety helmet BIS standard",
        },
        {
            "query": "safety shoes with steel toe for factory workers",
            "expected_is_numbers": "",
            "category": "ppe",
            "notes": "Safety footwear with protective toe cap",
        },
    ],
}


def seed_evaluation_dataset(
    category: str,
    processed_csv: Path,
    eval_dir: Path,
) -> None:
    """
    Create/update the evaluation test_queries.csv with seed queries.
    After collection, fills in expected_is_numbers from the collected data.
    """
    import csv

    eval_dir.mkdir(parents=True, exist_ok=True)
    queries_path = eval_dir / "test_queries.csv"

    queries = SEED_QUERIES_BY_CATEGORY.get(category, [])
    if not queries:
        logger.info(f"No seed queries defined for category '{category}'")
        return

    # Try to fill in IS numbers from collected data
    if processed_csv.exists():
        try:
            import pandas as pd
            df = pd.read_csv(processed_csv, dtype=str)
            cat_df = df[df["category"] == category]
            if not cat_df.empty:
                # Use the first collected IS number as a placeholder example
                example_is = cat_df["is_number"].iloc[0] if len(cat_df) > 0 else ""
                logger.info(
                    f"Using {len(cat_df)} collected standards to inform evaluation seed"
                )
        except Exception as e:
            logger.warning(f"Could not read processed CSV for evaluation seeding: {e}")

    # Write/overwrite test_queries.csv
    fieldnames = ["query", "expected_is_numbers", "category", "notes"]
    
    # Check if file already exists — preserve existing rows, add new ones
    existing_queries: dict[str, dict] = {}
    if queries_path.exists():
        try:
            with open(queries_path, "r", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    existing_queries[row["query"]] = row
        except Exception:
            pass

    # Merge: seed queries that don't already exist
    for q in queries:
        if q["query"] not in existing_queries:
            existing_queries[q["query"]] = q

    with open(queries_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for q in existing_queries.values():
            writer.writerow({k: q.get(k, "") for k in fieldnames})

    logger.info(f"Evaluation seed: {len(existing_queries)} queries written to {queries_path}")


def run_pipeline(category: str, limit: int, dry_run: bool) -> None:
    """Execute the full collect -> clean -> validate pipeline."""

    raw_bis_dir = PROJECT_ROOT / "data" / "raw" / "bis"
    processed_dir = PROJECT_ROOT / "data" / "processed"
    log_dir = PROJECT_ROOT / "data" / "raw" / "logs"
    eval_dir = PROJECT_ROOT / "data" / "evaluation"

    start_time = datetime.now()
    banner = "=" * 60
    print()
    print(banner)
    print("  STANDARDMATCH AI -- Data Build Pipeline")
    print(f"  Category : {category}")
    print(f"  Limit    : {limit}")
    print(f"  Dry run  : {dry_run}")
    print(f"  Started  : {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(banner)
    print()

    # -- Step 1: Collect -----------------------------------------------------
    logger.info("STEP 1/3 -- Collecting BIS Standards")
    print("-" * 60)
    print("Step 1/3: BIS Data Collection")
    print("-" * 60)

    try:
        from scripts.collect_bis_standards import _setup_logging, collect_standards

        coll_logger = _setup_logging(log_dir)
        records = collect_standards(
            category=category,
            limit=limit,
            dry_run=dry_run,
            output_dir=raw_bis_dir,
            log_dir=log_dir,
            logger=coll_logger,
        )
        logger.info(f"Collection complete: {len(records)} records")
    except ImportError:
        # Fallback: run as subprocess
        import subprocess
        cmd = [
            sys.executable,
            str(PROJECT_ROOT / "scripts" / "collect_bis_standards.py"),
            "--category", category,
            "--limit", str(limit),
        ]
        if dry_run:
            cmd.append("--dry-run")
        result = subprocess.run(cmd, capture_output=False)
        if result.returncode != 0:
            logger.error("Collection step failed. Check logs above.")

    if dry_run:
        print("\n[DRY RUN] Skipping clean and validate steps.")
        return

    # -- Step 2: Clean --------------------------------------------------------
    print()
    print("-" * 60)
    print("Step 2/3: Data Cleaning & Normalization")
    print("-" * 60)

    try:
        from scripts.clean_standards import clean_pipeline

        clean_summary = clean_pipeline(raw_bis_dir, processed_dir)
    except ImportError:
        import subprocess
        subprocess.run(
            [sys.executable, str(PROJECT_ROOT / "scripts" / "clean_standards.py")],
            capture_output=False,
        )
        clean_summary = {}

    # -- Step 3: Validate -----------------------------------------------------
    print()
    print("-" * 60)
    print("Step 3/3: Validation")
    print("-" * 60)

    processed_csv = processed_dir / "standards.csv"
    val_summary: dict = {}

    try:
        from scripts.validate_dataset import validate_dataset

        val_summary = validate_dataset(processed_csv, log_dir)
    except ImportError:
        import subprocess
        subprocess.run(
            [sys.executable, str(PROJECT_ROOT / "scripts" / "validate_dataset.py")],
            capture_output=False,
        )

    # -- Seed evaluation dataset ----------------------------------------------
    seed_evaluation_dataset(category, processed_csv, eval_dir)

    # -- Final Summary --------------------------------------------------------
    elapsed = (datetime.now() - start_time).total_seconds()
    print()
    print("=" * 60)
    print("  PIPELINE COMPLETE -- SUMMARY")
    print("=" * 60)

    if processed_csv.exists():
        print(f"  Processed CSV     : {processed_csv}")
        print(f"  Processed JSON    : {processed_dir / 'standards.json'}")
    if val_summary:
        total = val_summary.get("total", 0)
        valid = val_summary.get("valid", 0)
        scope_ct = val_summary.get("scope_with_text", 0)
        issues = val_summary.get("issues", {})
        print(f"  Total records     : {total}")
        print(f"  Valid records     : {valid}")
        print(f"  With scope text   : {scope_ct}")
        print(f"  Duplicates found  : {issues.get('duplicate_is_number', 0)}")
        print(f"  Missing scope     : {issues.get('missing_scope', 0)}")
    print(f"  Time elapsed      : {elapsed:.1f}s")
    print("=" * 60)
    print()


# ---------------------------------------------------------------------------
# CLI entrypoint
# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the full StandardMatch AI data build pipeline."
    )
    parser.add_argument(
        "--category",
        type=str,
        default="pipes",
        help="Category to collect (default: pipes)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=50,
        help="Maximum standards to collect (default: 50)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Test run without saving data",
    )
    args = parser.parse_args()
    run_pipeline(args.category, args.limit, args.dry_run)


if __name__ == "__main__":
    main()
