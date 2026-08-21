"""Wage annualization: convert whatever pay unit DOL used into an annual
figure so wages are comparable across rows.
"""
from __future__ import annotations

import re
from typing import Optional

import pandas as pd

# Standard full-time-equivalent multipliers used to annualize DOL wage data.
# Keys are pre-normalized with _normalize_unit() so lookups don't need to
# special-case punctuation/casing at call time.
_RAW_MULTIPLIERS = {
    "HOUR": 2080,
    "HOURLY": 2080,
    "HR": 2080,
    "WEEK": 52,
    "WEEKLY": 52,
    "WK": 52,
    "BIWEEKLY": 26,
    "BIWEEK": 26,
    "BIWKLY": 26,
    "SEMIMONTHLY": 24,
    "SEMIMONTH": 24,
    "MONTH": 12,
    "MONTHLY": 12,
    "MTH": 12,
    "YEAR": 1,
    "YEARLY": 1,
    "ANNUAL": 1,
    "YR": 1,
}


def _normalize_unit(unit: object) -> Optional[str]:
    if unit is None or (isinstance(unit, float) and pd.isna(unit)):
        return None
    s = re.sub(r"[^A-Z]", "", str(unit).upper())
    return s or None


ANNUALIZE_MULTIPLIERS = {_normalize_unit(k): v for k, v in _RAW_MULTIPLIERS.items()}


def annualize_wage(amount: object, unit: object) -> Optional[float]:
    """Convert a single wage amount + unit-of-pay string into an annual figure.

    Returns None if the amount is missing/non-numeric or the unit is
    unrecognized (rather than silently defaulting to a multiplier of 1,
    which would quietly understate hourly/weekly/monthly wages).
    """
    if amount is None or (isinstance(amount, float) and pd.isna(amount)):
        return None
    try:
        amount = float(amount)
    except (TypeError, ValueError):
        return None

    normalized_unit = _normalize_unit(unit)
    if normalized_unit is None:
        return None

    multiplier = ANNUALIZE_MULTIPLIERS.get(normalized_unit)
    if multiplier is None:
        return None

    return round(amount * multiplier, 2)


def annualize_wage_series(amount: pd.Series, unit: pd.Series) -> pd.Series:
    return pd.Series(
        [annualize_wage(a, u) for a, u in zip(amount, unit)],
        index=amount.index,
        dtype="float64",
    )
