"""Alias resolution pinned against the ACTUAL header rows DOL serves.

Transcribed from `run_pipeline.py --report-headers` run on a GitHub Actions
runner, 2026-08-24 (FY2024 Q4 / FY2025 Q4 / FY2026 Q3). These are the real
column names, not names taken from a record-layout PDF -- so if a future
DOL release renames something, these tests fail loudly instead of the
pipeline quietly emitting a column of nulls.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402

from src.columns import REQUIRED_FIELDS, load_alias_config, resolve_columns  # noqa: E402

# Abridged to the columns the pipeline actually consumes, plus a few
# neighbours -- the real files carry 98 (LCA) and 135-137 (PERM).
LCA_HEADERS = [
    "CASE_NUMBER", "CASE_STATUS", "RECEIVED_DATE", "DECISION_DATE",
    "ORIGINAL_CERT_DATE", "VISA_CLASS", "JOB_TITLE", "SOC_CODE", "SOC_TITLE",
    "FULL_TIME_POSITION", "BEGIN_DATE", "END_DATE", "TOTAL_WORKER_POSITIONS",
    "EMPLOYER_NAME", "TRADE_NAME_DBA", "EMPLOYER_CITY", "EMPLOYER_STATE",
    "WORKSITE_ADDRESS1", "WORKSITE_CITY", "WORKSITE_COUNTY", "WORKSITE_STATE",
    "WORKSITE_POSTAL_CODE", "WAGE_RATE_OF_PAY_FROM", "WAGE_RATE_OF_PAY_TO",
    "WAGE_UNIT_OF_PAY", "PREVAILING_WAGE", "PW_UNIT_OF_PAY", "PW_WAGE_LEVEL",
    "H_1B_DEPENDENT", "WILLFUL_VIOLATOR",
]

# FY2025 Q4 and FY2026 Q3 -- despite lacking "New_Form" in the filename,
# these carry revised-ETA-9089 column names.
PERM_FY2025_HEADERS = [
    "CASE_NUMBER", "CASE_STATUS", "RECEIVED_DATE", "DECISION_DATE",
    "OCCUPATION_TYPE", "EMP_BUSINESS_NAME", "EMP_TRADE_NAME", "EMP_CITY",
    "EMP_STATE", "EMP_NAICS", "JOB_OPP_PWD_NUMBER", "PWD_SOC_CODE",
    "PWD_SOC_TITLE", "JOB_TITLE", "JOB_OPP_WAGE_FROM", "JOB_OPP_WAGE_TO",
    "JOB_OPP_WAGE_PER", "JOB_OPP_WAGE_CONDITIONS", "PRIMARY_WORKSITE_CITY",
    "PRIMARY_WORKSITE_COUNTY", "PRIMARY_WORKSITE_STATE",
    "PRIMARY_WORKSITE_BLS_AREA", "OTHER_REQ_IS_FULLTIME_EMP",
]

# The FY2024 "New_Form" file -- same shape, but with NO SOC column at all.
PERM_FY2024_NEW_FORM_HEADERS = [
    h for h in PERM_FY2025_HEADERS if h not in ("PWD_SOC_CODE", "PWD_SOC_TITLE")
]


@pytest.fixture
def cfg():
    return load_alias_config()


def test_lca_every_field_resolves(cfg):
    r = resolve_columns(LCA_HEADERS, "LCA", "LCA_Disclosure_Data_FY2026_Q3.xlsx", cfg)
    assert r.get("employer_raw") == "EMPLOYER_NAME"
    assert r.get("job_title_raw") == "JOB_TITLE"
    assert r.get("soc_code") == "SOC_CODE"
    assert r.get("worksite_city") == "WORKSITE_CITY"
    assert r.get("worksite_state") == "WORKSITE_STATE"
    assert r.get("wage_from") == "WAGE_RATE_OF_PAY_FROM"
    assert r.get("wage_unit") == "WAGE_UNIT_OF_PAY"
    assert r.get("wage_level") == "PW_WAGE_LEVEL"
    assert r.get("full_time_flag") == "FULL_TIME_POSITION"
    for field in REQUIRED_FIELDS:
        assert r.get(field) is not None


@pytest.mark.parametrize("kind", ["PERM_LEGACY", "PERM_REVISED"])
def test_perm_resolves_revised_names_under_either_kind(cfg, kind):
    # Both labels must work: the FY2025/FY2026 files are classified
    # PERM_LEGACY by filename but actually carry revised-form columns.
    r = resolve_columns(PERM_FY2025_HEADERS, kind, "PERM_Disclosure_Data_FY2025_Q4.xlsx", cfg)
    assert r.get("employer_raw") == "EMP_BUSINESS_NAME"
    assert r.get("job_title_raw") == "JOB_TITLE"
    assert r.get("soc_code") == "PWD_SOC_CODE"
    assert r.get("worksite_city") == "PRIMARY_WORKSITE_CITY"
    assert r.get("worksite_state") == "PRIMARY_WORKSITE_STATE"
    assert r.get("wage_from") == "JOB_OPP_WAGE_FROM"
    assert r.get("wage_to") == "JOB_OPP_WAGE_TO"
    assert r.get("wage_unit") == "JOB_OPP_WAGE_PER"
    assert r.get("full_time_flag") == "OTHER_REQ_IS_FULLTIME_EMP"
    for field in REQUIRED_FIELDS:
        assert r.get(field) is not None


def test_perm_wage_level_absent_but_does_not_abort(cfg):
    # The revised ETA-9089 dropped the prevailing wage level field, so
    # signal 4 is LCA-only. This must degrade to None, not raise.
    r = resolve_columns(PERM_FY2025_HEADERS, "PERM_REVISED", "perm.xlsx", cfg)
    assert r.get("wage_level") is None


def test_perm_fy2024_new_form_has_no_soc_and_still_resolves(cfg):
    r = resolve_columns(
        PERM_FY2024_NEW_FORM_HEADERS,
        "PERM_REVISED",
        "PERM_Disclosure_Data_New_Form_FY2024_Q4.xlsx",
        cfg,
    )
    assert r.get("soc_code") is None  # falls back to title-keyword classification
    assert r.get("employer_raw") == "EMP_BUSINESS_NAME"
    for field in REQUIRED_FIELDS:
        assert r.get(field) is not None
