"""The five signals: structured answers about what an employer actually
filed. No formatting, no presentation, no prediction -- this layer reports
what is in the data and nothing more.

Every count here is of CERTIFIED / CERTIFIED-WITHDRAWN filings only.
Denied and withdrawn rows stay in the table (flagged) so denial rate can
be computed, but they never inflate a "does this employer sponsor" answer.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional

import pandas as pd

from .employer_normalize import normalize_employer_name


def main_counts_only(df: pd.DataFrame) -> pd.DataFrame:
    """CERTIFIED and CERTIFIED-WITHDRAWN rows only."""
    return df.loc[~df["is_denied_or_withdrawn"]]


def _employer_rows(df: pd.DataFrame, employer_normalized: str) -> pd.DataFrame:
    if "employer_normalized" in df.columns:
        col = df["employer_normalized"]
    else:
        col = df["employer_raw"].map(normalize_employer_name)
    return df.loc[col == employer_normalized]


@dataclass
class EmployerSignals:
    employer_normalized: str
    role_bucket: str
    window_fiscal_years: List[int]

    # Signal 1: does this employer file at all
    total_certified_filings: int = 0

    # Signal 2: do they file for THIS role
    role_bucket_filings: int = 0

    # Signal 3: are they still filing
    filings_by_fiscal_year: Dict[int, int] = field(default_factory=dict)
    role_filings_by_fiscal_year: Dict[int, int] = field(default_factory=dict)
    stopped_filing: bool = False

    # Signal 4: do they file at THIS level
    wage_level_distribution: Dict[str, int] = field(default_factory=dict)
    wage_min: Optional[float] = None
    wage_median: Optional[float] = None
    wage_max: Optional[float] = None

    # Signal 5: does it convert
    has_certified_perm: bool = False
    perm_filings: int = 0
    lca_filings: int = 0
    uscis_approvals: Optional[int] = None
    uscis_data_available: bool = False

    # Honesty
    denied_or_withdrawn_filings: int = 0

    def to_dict(self) -> dict:
        return asdict(self)


def employer_signals(
    df: pd.DataFrame,
    employer_normalized: str,
    role_bucket: str,
) -> EmployerSignals:
    """All five signals for one employer + role bucket."""
    window_years = sorted(int(y) for y in df["fiscal_year"].dropna().unique())

    all_rows = _employer_rows(df, employer_normalized)
    certified = main_counts_only(all_rows)
    role_rows = certified.loc[certified["role_bucket"] == role_bucket]

    by_year = {
        int(y): int(c)
        for y, c in certified["fiscal_year"].dropna().value_counts().sort_index().items()
    }
    role_by_year = {
        int(y): int(c)
        for y, c in role_rows["fiscal_year"].dropna().value_counts().sort_index().items()
    }
    # Fill gaps so a zero year is visibly zero rather than missing.
    by_year = {y: by_year.get(y, 0) for y in window_years}
    role_by_year = {y: role_by_year.get(y, 0) for y in window_years}

    # "Stopped filing" = nothing in the most recent year, but something
    # earlier. Reported as its own flag rather than folded into the total.
    stopped = False
    if window_years:
        latest = window_years[-1]
        earlier = [by_year.get(y, 0) for y in window_years[:-1]]
        stopped = by_year.get(latest, 0) == 0 and any(c > 0 for c in earlier)

    levels = (
        role_rows["wage_level"].dropna().astype(str).str.strip().replace("", pd.NA).dropna()
    )
    level_dist = {str(k): int(v) for k, v in levels.value_counts().sort_index().items()}

    wages = pd.to_numeric(role_rows["wage_offered"], errors="coerce").dropna()

    perm_rows = certified.loc[certified["program"] == "PERM"]
    lca_rows = certified.loc[certified["program"] == "LCA"]

    return EmployerSignals(
        employer_normalized=employer_normalized,
        role_bucket=role_bucket,
        window_fiscal_years=window_years,
        total_certified_filings=int(len(certified)),
        role_bucket_filings=int(len(role_rows)),
        filings_by_fiscal_year=by_year,
        role_filings_by_fiscal_year=role_by_year,
        stopped_filing=bool(stopped),
        wage_level_distribution=level_dist,
        wage_min=float(wages.min()) if not wages.empty else None,
        wage_median=float(wages.median()) if not wages.empty else None,
        wage_max=float(wages.max()) if not wages.empty else None,
        has_certified_perm=bool(len(perm_rows) > 0),
        perm_filings=int(len(perm_rows)),
        lca_filings=int(len(lca_rows)),
        # USCIS H-1B Employer Data Hub is a separate source not ingested by
        # this pipeline yet. Reported as unavailable rather than as zero --
        # "no data" and "zero approvals" mean very different things.
        uscis_approvals=None,
        uscis_data_available=False,
        denied_or_withdrawn_filings=int(all_rows["is_denied_or_withdrawn"].sum()),
    )


def _metro_series(df: pd.DataFrame) -> pd.Series:
    if "metro" in df.columns:
        return df["metro"]
    city = df["worksite_city"].fillna("").astype(str).str.strip().str.upper()
    state = df["worksite_state"].fillna("").astype(str).str.strip().str.upper()
    return city + ", " + state


def rank_employers_for_bucket_metro(
    df: pd.DataFrame,
    role_bucket: str,
    metro: Optional[str] = None,
    recent_fiscal_years: int = 1,
    top_n: int = 50,
) -> pd.DataFrame:
    """Employers ranked by RECENT filing volume in a bucket (and metro),
    with wage range and level mix -- the paid-list query.

    Ranked on the most recent `recent_fiscal_years` so employers who have
    stopped filing don't top a list of who to apply to today.
    """
    certified = main_counts_only(df)
    subset = certified.loc[certified["role_bucket"] == role_bucket].copy()

    if metro:
        subset = subset.loc[_metro_series(subset).str.upper() == metro.strip().upper()]

    window_years = sorted(int(y) for y in df["fiscal_year"].dropna().unique())
    recent_years = window_years[-recent_fiscal_years:] if window_years else []
    if recent_years:
        subset = subset.loc[subset["fiscal_year"].isin(recent_years)]

    if subset.empty:
        return pd.DataFrame(
            columns=[
                "employer_normalized",
                "filing_count",
                "wage_min",
                "wage_median",
                "wage_max",
                "level_mix",
            ]
        )

    if "employer_normalized" not in subset.columns:
        subset["employer_normalized"] = subset["employer_raw"].map(normalize_employer_name)

    subset["wage_offered"] = pd.to_numeric(subset["wage_offered"], errors="coerce")

    ranked = (
        subset.groupby("employer_normalized")
        .agg(
            filing_count=("employer_normalized", "size"),
            wage_min=("wage_offered", "min"),
            wage_median=("wage_offered", "median"),
            wage_max=("wage_offered", "max"),
            level_mix=(
                "wage_level",
                lambda s: "; ".join(
                    f"{k}:{v}"
                    for k, v in s.dropna().astype(str).str.strip().replace("", pd.NA).dropna().value_counts().sort_index().items()
                ),
            ),
        )
        .reset_index()
        .sort_values("filing_count", ascending=False)
    )
    return ranked.head(top_n).reset_index(drop=True)


@dataclass
class WageStats:
    role_bucket: str
    metro: Optional[str]
    filing_count: int
    median: Optional[float]
    p25: Optional[float]
    p75: Optional[float]

    def to_dict(self) -> dict:
        return asdict(self)


def wage_stats_for_bucket_metro(
    df: pd.DataFrame, role_bucket: str, metro: Optional[str] = None
) -> WageStats:
    """Median and interquartile range of annualized wage across ALL
    employers -- the shareable number."""
    certified = main_counts_only(df)
    subset = certified.loc[certified["role_bucket"] == role_bucket]

    if metro:
        subset = subset.loc[_metro_series(subset).str.upper() == metro.strip().upper()]

    wages = pd.to_numeric(subset["wage_offered"], errors="coerce").dropna()
    if wages.empty:
        return WageStats(role_bucket, metro, 0, None, None, None)

    return WageStats(
        role_bucket=role_bucket,
        metro=metro,
        filing_count=int(len(wages)),
        median=float(wages.median()),
        p25=float(wages.quantile(0.25)),
        p75=float(wages.quantile(0.75)),
    )
