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
from .build_index import write_index
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

    # Oldest release first, so that when the same case appears in more than
    # one quarterly file the de-duplication below keeps the newest version
    # of it (a case can be re-issued with a different final status).
    data_entries = sorted(
        (e for e in manifest if e["kind"] != "LAYOUT"),
        key=lambda e: (e.get("fiscal_year") or 0, e.get("quarter") or 99),
    )

    for entry in data_entries:
        kind = entry["kind"]
        local_path = Path(entry["local_path"])
        if kind == "LCA":
            normalized_df, dropped, unknown_statuses = parse_lca_file(local_path)
        else:
            normalized_df, dropped, unknown_statuses = parse_perm_file(
                local_path, file_kind=kind
            )
        if unknown_statuses:
            logger.warning(
                "%s: dropped %d rows with unrecognized case_status: %s",
                local_path.name,
                dropped,
                unknown_statuses,
            )

        raw_rows = len(normalized_df) + dropped
        per_file_stats.append(
            {
                "source_file": local_path.name,
                "kind": kind,
                "fiscal_year": entry.get("fiscal_year"),
                "quarter": entry.get("quarter"),
                "raw_rows": raw_rows,
                "kept_rows": len(normalized_df),
                "dropped_unknown_status": dropped,
                "unknown_statuses": unknown_statuses,
            }
        )
        normalized_frames.append(normalized_df)

    if not normalized_frames:
        raise RuntimeError("No data files were parsed -- nothing to combine.")

    combined_df = pd.concat(normalized_frames, ignore_index=True)

    # This is what makes ingesting every quarter safe, and it is also the
    # measurement that settles whether OFLC's quarterly releases are
    # cumulative or incremental (see discover_sources.select_sources).
    #
    #   near-zero duplicates -> the quarters are disjoint increments
    #   large duplicate share -> the releases are cumulative year-to-date
    #
    # Either way the result is right: keep="last" retains the newest release
    # of each case, since frames were concatenated oldest-first.
    rows_before = len(combined_df)
    has_case = combined_df["case_number"].notna() & (combined_df["case_number"] != "")
    dupe_mask = combined_df.loc[has_case].duplicated(subset=["case_number"], keep="last")
    duplicate_rows = int(dupe_mask.sum())
    if duplicate_rows:
        combined_df = combined_df.drop(
            index=combined_df.loc[has_case].index[dupe_mask]
        ).reset_index(drop=True)
    logger.info(
        "Duplicate case_numbers across releases: %d of %d rows (%.2f%%) -- %s",
        duplicate_rows,
        rows_before,
        100 * duplicate_rows / rows_before if rows_before else 0.0,
        "releases look CUMULATIVE" if duplicate_rows > rows_before * 0.1
        else "releases look INCREMENTAL",
    )

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

    # The static payload the front end queries directly. Built here so a
    # quarterly rerun refreshes the site's data in the same pass.
    index_path = write_index(combined_df)
    logger.info("Wrote browser index to %s", index_path)

    report = build_report(per_file_stats, combined_df)
    report["duplicate_case_numbers_dropped"] = duplicate_rows
    write_report(report)
    print_report(report)

    return report
