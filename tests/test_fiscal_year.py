import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd  # noqa: E402

from src.fiscal_year import fiscal_year_from_date, fiscal_year_series  # noqa: E402


def test_fy_before_october():
    assert fiscal_year_from_date("2025-03-15") == 2025


def test_fy_on_october_first():
    assert fiscal_year_from_date("2025-10-01") == 2026


def test_fy_december():
    assert fiscal_year_from_date("2025-12-31") == 2026


def test_fy_september_last_day():
    assert fiscal_year_from_date("2026-09-30") == 2026


def test_fy_none_input():
    assert fiscal_year_from_date(None) is None


def test_fy_series():
    s = pd.Series(["2025-03-15", "2025-10-01", None])
    result = fiscal_year_series(s)
    assert result.iloc[0] == 2025
    assert result.iloc[1] == 2026
    assert pd.isna(result.iloc[2])
