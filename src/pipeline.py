"""Orchestrates one end-to-end pipeline run: discover -> download -> parse
-> normalize -> combine -> write output -> report row counts.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import List

import pandas as pd

from .discover_sources import PERFORMANCE_PAGE, get_sources
from .download import download_sources
from .employer_normalize import normalize_employer_name
from .employer_top_n import write_top_employers
from .parse_lca import parse_lca_file
from .parse_perm import parse_perm_file
from .report import build_report, print_report, write_report
from .role_taxonomy import classify_dataframe
from .unmatched_titles import write_top_unmatched_titles

logger = logging.getLogger(__name__)

PROCESSED_DIR = Path(__file__).resolve().parent.parent / "data" / "processed"
OUTPUT_PARQUET = PROCESSED_DIR / "dol_filings.parquet"
OUTPUT_CSV = PROCESSED_DIR / "dol_filings.csv"


def run(
    page_url: str = PERFORMANCE_PAGE,
    lca_years: int = 3,
    perm_years: int = 2,
    force_download: bool = False,
) -> dict:
    logger.info("Discovering source files from %s", page_url)
    sources = get_sources(page_url=page_url, lca_years=lca_years, perm_years=perm_years)

    logger.info("Selected %d files (incl. record layouts)", len(sources))
    for s in sources:
        logger.info("  [%s] FY%s %s", s.kind, s.fiscal_year, s.url)

    manifest = download_sources(sources, force=force_download)

    per_file_stats: List[dict] = []
    normalized_frames: List[pd.DataFrame] = []

    for entry in manifest:
        kind = entry["kind"]
        if kind == "LAYOUT":
            continue

        local_path = Path(entry["local_path"])
        if kind == "LCA":
            normalized_df, dropped = parse_lca_file(local_path)
        else:
            normalized_df, dropped = parse_perm_file(local_path, file_kind=kind)

        raw_rows = len(normalized_df) + dropped
        per_file_stats.append(
            {
                "source_file": local_path.name,
                "kind": kind,
                "fiscal_year": entry.get("fiscal_year"),
                "raw_rows": raw_rows,
                "kept_rows": len(normalized_df),
                "dropped_unknown_status": dropped,
            }
        )
        normalized_frames.append(normalized_df)

    if not normalized_frames:
        raise RuntimeError("No data files were parsed -- nothing to combine.")

    combined_df = pd.concat(normalized_frames, ignore_index=True)

    combined_df["employer_normalized"] = combined_df["employer_raw"].map(normalize_employer_name)
    combined_df = classify_dataframe(combined_df)

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    combined_df.to_parquet(OUTPUT_PARQUET, index=False)
    combined_df.to_csv(OUTPUT_CSV, index=False)
    logger.info("Wrote %d rows to %s and %s", len(combined_df), OUTPUT_PARQUET, OUTPUT_CSV)

    # Both feed the hand-curation passes described in README.md.
    top_employers_path = write_top_employers(combined_df)
    unmatched_path = write_top_unmatched_titles(combined_df)
    logger.info("Wrote %s and %s", top_employers_path, unmatched_path)

    report = build_report(per_file_stats, combined_df)
    write_report(report)
    print_report(report)

    return report
