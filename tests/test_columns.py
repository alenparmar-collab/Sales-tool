import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.columns import ColumnResolutionError, resolve_columns  # noqa: E402

ALIAS_CONFIG = {
    "LCA": {
        "case_status": ["CASE_STATUS"],
        "decision_date": ["DECISION_DATE"],
        "employer_raw": ["EMPLOYER_NAME"],
        "job_title_raw": ["JOB_TITLE"],
        "worksite_city": ["WORKSITE_CITY"],
        "worksite_state": ["WORKSITE_STATE"],
        "wage_from": ["WAGE_RATE_OF_PAY_FROM"],
        "wage_unit": ["WAGE_UNIT_OF_PAY"],
    }
}


def test_exact_match():
    headers = ["CASE_STATUS", "DECISION_DATE", "EMPLOYER_NAME", "JOB_TITLE",
               "WORKSITE_CITY", "WORKSITE_STATE", "WAGE_RATE_OF_PAY_FROM", "WAGE_UNIT_OF_PAY"]
    resolved = resolve_columns(headers, "LCA", "test.xlsx", ALIAS_CONFIG)
    assert resolved.get("employer_raw") == "EMPLOYER_NAME"


def test_case_and_whitespace_insensitive_header_match():
    headers = [" case status ", "decision_date", "employer name", "job_title",
               "worksite city", "worksite_state", "wage rate of pay from", "wage_unit_of_pay"]
    resolved = resolve_columns(headers, "LCA", "test.xlsx", ALIAS_CONFIG)
    assert resolved.get("employer_raw") == "employer name"
    assert resolved.get("case_status") == " case status "


def test_missing_required_field_raises_with_diagnostics():
    headers = ["CASE_STATUS", "DECISION_DATE", "JOB_TITLE",
               "WORKSITE_CITY", "WORKSITE_STATE", "WAGE_RATE_OF_PAY_FROM", "WAGE_UNIT_OF_PAY"]
    with pytest.raises(ColumnResolutionError) as exc_info:
        resolve_columns(headers, "LCA", "test.xlsx", ALIAS_CONFIG)
    msg = str(exc_info.value)
    assert "employer_raw" in msg
    assert "test.xlsx" in msg


def test_close_but_renamed_header_suggests_but_still_fails():
    # Simulates a year where DOL renamed EMPLOYER_NAME -> EMPLOYER_BUSINESS_NAME
    # and that alias hasn't been added to config yet: should fail loudly with
    # a suggestion rather than silently leaving the field blank.
    headers = ["CASE_STATUS", "DECISION_DATE", "EMPLOYER_BUSINESS_NAME", "JOB_TITLE",
               "WORKSITE_CITY", "WORKSITE_STATE", "WAGE_RATE_OF_PAY_FROM", "WAGE_UNIT_OF_PAY"]
    with pytest.raises(ColumnResolutionError):
        resolve_columns(headers, "LCA", "test.xlsx", ALIAS_CONFIG)


def test_unknown_file_kind_raises():
    with pytest.raises(ColumnResolutionError):
        resolve_columns(["CASE_STATUS"], "NOT_A_KIND", "test.xlsx", ALIAS_CONFIG)
