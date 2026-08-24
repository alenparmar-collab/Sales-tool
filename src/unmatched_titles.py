"""Report the most common job titles that fell through to 'other'.

Per the build brief this is the highest-value manual step in the whole
taxonomy: reviewing the top unmatched titles once and hand-adding them to
config/role_taxonomy.yaml beats any clever matching algorithm.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import pandas as pd

PROCESSED_DIR = Path(__file__).resolve().parent.parent / "data" / "processed"
DEFAULT_OUTPUT = PROCESSED_DIR / "unmatched_titles_top_100.csv"


def top_unmatched_titles(df: pd.DataFrame, top_n: int = 100) -> pd.DataFrame:
    unmatched = df[df["role_bucket"] == "other"].copy()
    if unmatched.empty:
        return pd.DataFrame(columns=["job_title_raw", "filing_count", "sample_soc_codes"])

    grouped = (
        unmatched.groupby("job_title_raw")
        .agg(
            filing_count=("job_title_raw", "size"),
            sample_soc_codes=(
                "soc_code",
                lambda s: "; ".join(sorted({str(v) for v in s if pd.notna(v)})[:5]),
            ),
        )
        .reset_index()
        .sort_values("filing_count", ascending=False)
    )
    return grouped.head(top_n).reset_index(drop=True)


def write_top_unmatched_titles(
    df: pd.DataFrame, top_n: int = 100, output_path: Optional[Path] = None
) -> Path:
    output_path = output_path or DEFAULT_OUTPUT
    output_path.parent.mkdir(parents=True, exist_ok=True)
    top_unmatched_titles(df, top_n=top_n).to_csv(output_path, index=False)
    return output_path
