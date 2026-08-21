"""Federal fiscal year helpers. FY runs Oct 1 (prior calendar year) through
Sep 30. E.g. 2025-11-15 is in FY2026; 2025-03-15 is in FY2025.
"""
from __future__ import annotations

from typing import Optional

import pandas as pd


def fiscal_year_from_date(d: object) -> Optional[int]:
    ts = pd.to_datetime(d, errors="coerce")
    if pd.isna(ts):
        return None
    return int(ts.year + 1) if ts.month >= 10 else int(ts.year)


def fiscal_year_series(dates: pd.Series) -> pd.Series:
    parsed = pd.to_datetime(dates, errors="coerce")
    fy = parsed.dt.year + (parsed.dt.month >= 10).astype("Int64")
    return fy.astype("Int64")


def last_n_fiscal_years(current_fy: int, n: int) -> list[int]:
    return list(range(current_fy - n + 1, current_fy + 1))
