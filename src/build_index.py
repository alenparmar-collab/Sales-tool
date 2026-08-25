"""Collapse the normalized filing table into a compact index the browser
can query directly, with no backend.

The row-level table is ~2M records and will never fit in a page. But the
tool never needs a row: every one of the five signals is a count, a
distribution or a percentile over (employer x role bucket x fiscal year).
Pre-aggregating to that grain turns millions of rows into tens of
thousands of records, which is small enough to ship as a static file on
Netlify's free tier -- no database, no API, no per-query cost.

Two things keep the size down:

  * Short JSON keys. At tens of thousands of records, "software_engineer"
    repeated as a key costs more than the values.
  * A filing-count floor. The long tail is employers with one or two
    lifetime filings, which nobody types into the box. They are excluded
    from the detail payload but still counted in the totals, so the
    headline figures stay true.

Wage percentiles are computed here rather than in the browser because
doing it here costs nothing and shipping the wage vectors needed to do it
client-side would cost more than the whole rest of the index.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import pandas as pd

from .signals import main_counts_only

logger = logging.getLogger(__name__)

PROCESSED_DIR = Path(__file__).resolve().parent.parent / "data" / "processed"
WEB_DATA_DIR = Path(__file__).resolve().parent.parent / "web" / "data"
DEFAULT_INPUT = PROCESSED_DIR / "dol_filings.parquet"
DEFAULT_OUTPUT = WEB_DATA_DIR / "index.json"

# Employers below this many certified filings across the whole window are
# left out of the detail payload. They stay in the totals.
MIN_FILINGS = 3

# Wage percentiles are only published for metros with enough filings in a
# bucket for the number to mean anything.
MIN_WAGE_SAMPLE = 20
MAX_METROS = 60


def _metro_series(df: pd.DataFrame) -> pd.Series:
    city = df["worksite_city"].fillna("").astype(str).str.strip().str.upper()
    state = df["worksite_state"].fillna("").astype(str).str.strip().str.upper()
    return (city + ", " + state).where(city.ne("") & state.ne(""), other=pd.NA)


def _wage_triplet(wages: pd.Series) -> Optional[list]:
    w = pd.to_numeric(wages, errors="coerce").dropna()
    if w.empty:
        return None
    return [int(w.min()), int(w.median()), int(w.max())]


def build_index(
    df: pd.DataFrame,
    min_filings: int = MIN_FILINGS,
    fiscal_years: Optional[list] = None,
) -> dict:
    certified = main_counts_only(df).copy()
    certified["metro"] = _metro_series(certified)

    years = fiscal_years or sorted(
        int(y) for y in certified["fiscal_year"].dropna().unique()
    )
    year_pos = {y: i for i, y in enumerate(years)}

    def year_vector(frame: pd.DataFrame) -> list:
        vec = [0] * len(years)
        for y, c in frame["fiscal_year"].dropna().value_counts().items():
            if int(y) in year_pos:
                vec[year_pos[int(y)]] = int(c)
        return vec

    totals = certified.groupby("employer_normalized").size()
    keep = set(totals[totals >= min_filings].index)
    logger.info(
        "Employers: %d total, %d at or above the %d-filing floor (%.1f%% of filings kept in detail)",
        len(totals),
        len(keep),
        min_filings,
        100 * totals[totals >= min_filings].sum() / max(totals.sum(), 1),
    )

    employers = []
    detail = certified[certified["employer_normalized"].isin(keep)]

    for name, grp in detail.groupby("employer_normalized", sort=False):
        perm_count = int((grp["program"] == "PERM").sum())
        record = {
            "n": name,
            "t": int(len(grp)),
            "y": year_vector(grp),
            "p": perm_count,
            "b": {},
        }

        for bucket, bgrp in grp.groupby("role_bucket", sort=False):
            if bucket == "other" and len(bgrp) < min_filings:
                continue
            levels = (
                bgrp["wage_level"].dropna().astype(str).str.strip().replace("", pd.NA).dropna()
            )
            entry = {"t": int(len(bgrp)), "y": year_vector(bgrp)}
            if not levels.empty:
                entry["l"] = {str(k): int(v) for k, v in levels.value_counts().items()}
            triplet = _wage_triplet(bgrp["wage_offered"])
            if triplet:
                entry["w"] = triplet
            record["b"][str(bucket)] = entry

        employers.append(record)

    employers.sort(key=lambda r: -r["t"])

    # Median and IQR per bucket x metro -- the shareable number, and the
    # only part of the index not keyed by employer.
    wage_stats = {}
    metro_volume = certified["metro"].value_counts().head(MAX_METROS)
    top_metros = set(metro_volume.index)
    wage_frame = certified[certified["metro"].isin(top_metros)]

    for (bucket, metro), grp in wage_frame.groupby(["role_bucket", "metro"], sort=False):
        w = pd.to_numeric(grp["wage_offered"], errors="coerce").dropna()
        if len(w) < MIN_WAGE_SAMPLE:
            continue
        wage_stats[f"{bucket}|{metro}"] = [
            int(w.quantile(0.25)),
            int(w.median()),
            int(w.quantile(0.75)),
            int(len(w)),
        ]

    return {
        "meta": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source": "U.S. Department of Labor, Office of Foreign Labor Certification",
            "source_url": "https://www.dol.gov/agencies/eta/foreign-labor/performance",
            "fiscal_years": years,
            "min_filings_threshold": min_filings,
            "employers_in_index": len(employers),
            "employers_total": int(len(totals)),
            "filings_counted": int(len(certified)),
            # Stated so the UI can say it plainly rather than implying the
            # index is every employer that has ever filed.
            "note": (
                "Counts are certified and certified-withdrawn determinations only. "
                f"Employers with fewer than {min_filings} filings in the window are "
                "counted in the totals but omitted from per-employer detail."
            ),
        },
        "metros": sorted(top_metros),
        "employers": employers,
        "wage_stats": wage_stats,
    }


def write_index(
    df: pd.DataFrame,
    output_path: Optional[Path] = None,
    min_filings: int = MIN_FILINGS,
) -> Path:
    output_path = output_path or DEFAULT_OUTPUT
    output_path.parent.mkdir(parents=True, exist_ok=True)

    index = build_index(df, min_filings=min_filings)
    with open(output_path, "w") as f:
        json.dump(index, f, separators=(",", ":"))

    size_mb = output_path.stat().st_size / (1024 ** 2)
    logger.info(
        "Wrote %s: %.1f MB, %d employers, %d wage-stat entries",
        output_path,
        size_mb,
        len(index["employers"]),
        len(index["wage_stats"]),
    )
    if size_mb > 50:
        logger.warning(
            "Index is %.1f MB, above the ~50 MB static-hosting target. Raise "
            "MIN_FILINGS or shard the payload before shipping it to browsers.",
            size_mb,
        )
    return output_path
