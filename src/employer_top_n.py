"""Rank normalized employers by filing volume, for hand-building the
top-500 alias map (config/employer_aliases.yaml). Counts only main-count
rows (CERTIFIED / CERTIFIED-WITHDRAWN) -- denied/withdrawn filings
shouldn't inflate an employer's apparent sponsorship volume.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import pandas as pd

from .employer_normalize import normalize_employer_name

PROCESSED_DIR = Path(__file__).resolve().parent.parent / "data" / "processed"
DEFAULT_OUTPUT = PROCESSED_DIR / "top_500_employers.csv"


def rank_employers(df: pd.DataFrame, top_n: int = 500) -> pd.DataFrame:
    main = df.loc[~df["is_denied_or_withdrawn"]].copy()
    main["employer_normalized"] = main["employer_raw"].map(normalize_employer_name)
    main = main[main["employer_normalized"] != ""]

    grouped = (
        main.groupby("employer_normalized")
        .agg(
            filing_count=("employer_raw", "size"),
            sample_raw_variants=("employer_raw", lambda s: "; ".join(sorted(set(s))[:5])),
            distinct_raw_variants=("employer_raw", lambda s: s.nunique()),
        )
        .reset_index()
        .sort_values("filing_count", ascending=False)
    )

    return grouped.head(top_n).reset_index(drop=True)


def write_top_employers(
    df: pd.DataFrame, top_n: int = 500, output_path: Optional[Path] = None
) -> Path:
    output_path = output_path or DEFAULT_OUTPUT
    output_path.parent.mkdir(parents=True, exist_ok=True)
    ranked = rank_employers(df, top_n=top_n)
    ranked.to_csv(output_path, index=False)
    return output_path
