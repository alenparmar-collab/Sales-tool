import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.wage import annualize_wage  # noqa: E402


def test_hourly():
    assert annualize_wage(25.0, "Hour") == 25.0 * 2080


def test_weekly():
    assert annualize_wage(1000, "Week") == 52000


def test_biweekly():
    assert annualize_wage(2000, "Bi-Weekly") == 52000


def test_semimonthly():
    assert annualize_wage(3000, "Semi-Monthly") == 72000


def test_monthly():
    assert annualize_wage(5000, "Month") == 60000


def test_year():
    assert annualize_wage(90000, "Year") == 90000


def test_annual_variant():
    assert annualize_wage(90000, "Annual") == 90000


def test_unknown_unit_returns_none():
    assert annualize_wage(90000, "Fortnight") is None


def test_missing_amount_returns_none():
    assert annualize_wage(None, "Year") is None


def test_missing_unit_returns_none():
    assert annualize_wage(90000, None) is None


def test_non_numeric_amount_returns_none():
    assert annualize_wage("N/A", "Year") is None


def test_case_and_whitespace_insensitive():
    assert annualize_wage(25.0, "  hour ") == 25.0 * 2080
    assert annualize_wage(25.0, "HOURLY") == 25.0 * 2080
