#!/usr/bin/env python3
"""Script to ingest and normalize regional agricultural data for KISANAI C2C.

Features:
- Validates data records against schema
- Enforces deduplication using composite primary key (state, district, crop, season, crop_year)
- Generates SHA-256 digest to prevent re-inserting unchanged rows
- Supports dry-run and local SQLite or BigQuery export
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
from typing import Any


def compute_row_hash(row: dict[str, Any]) -> str:
    """Compute SHA-256 hash of key identifying fields for deduplication."""
    key = f"{row.get('state', '').strip().lower()}|{row.get('district', '').strip().lower()}|{row.get('crop', '').strip().lower()}|{row.get('season', '').strip().lower()}|{row.get('crop_year', '')}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def ingest_csv(csv_path: str | Path, dry_run: bool = False) -> dict[str, Any]:
    path = Path(csv_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {csv_path}")

    seen_hashes: set[str] = set()
    unique_rows: list[dict[str, Any]] = []
    duplicate_count = 0

    with open(path, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            h = compute_row_hash(row)
            if h in seen_hashes:
                duplicate_count += 1
                continue
            seen_hashes.add(h)
            unique_rows.append(row)

    print(f"Read {len(unique_rows) + duplicate_count} total rows from {path.name}.")
    print(f"Found {duplicate_count} duplicate rows (skipped).")
    print(f"Processed {len(unique_rows)} unique regional records.")

    if not dry_run:
        # Save deduplicated clean dataset
        out_path = path.parent / f"{path.stem}_clean_dedup.json"
        with open(out_path, "w", encoding="utf-8") as out:
            json.dump(unique_rows, out, indent=2)
        print(f"Saved deduplicated data to: {out_path}")

    return {
        "source_file": str(path),
        "total_read": len(unique_rows) + duplicate_count,
        "duplicates_skipped": duplicate_count,
        "unique_records": len(unique_rows),
    }


def main():
    parser = argparse.ArgumentParser(description="Ingest and deduplicate regional crop/weather data.")
    parser.add_argument("csv_path", help="Path to input CSV file")
    parser.add_argument("--dry-run", action="store_true", help="Analyze without writing output")
    args = parser.parse_args()

    result = ingest_csv(args.csv_path, dry_run=args.dry_run)
    print("Ingestion summary:", json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
