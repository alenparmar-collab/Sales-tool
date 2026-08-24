import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd  # noqa: E402
import pytest  # noqa: E402

from src.signals import (  # noqa: E402
    employer_signals,
    rank_employers_for_bucket_metro,
    wage_stats_for_bucket_metro,
)


def _row(**kwargs):
    base = {
        "employer_raw": "Acme Corp",
        "employer_normalized": "ACME",
        "program": "LCA",
        "fiscal_year": 2026,
        "case_status": "CERTIFIED",
        "is_denied_or_withdrawn": False,
        "job_title_raw": "Software Engineer",
        "soc_code": "15-1252",
        "role_bucket": "software_engineer",
        "seniority": None,
        "worksite_city": "Austin",
        "worksite_state": "TX",
        "wage_offered": 120000.0,
        "wage_level": "II",
    }
    base.update(kwargs)
    return base


@pytest.fixture
def df():
    return pd.DataFrame(
        [
            # Acme: files across all 3 years, both roles, both programs
            _row(fiscal_year=2024, wage_offered=100000.0, wage_level="I"),
            _row(fiscal_year=2025, wage_offered=120000.0, wage_level="II"),
            _row(fiscal_year=2026, wage_offered=140000.0, wage_level="III"),
            _row(fiscal_year=2026, role_bucket="qa_engineer", wage_offered=90000.0, wage_level="I"),
            _row(fiscal_year=2026, program="PERM", wage_offered=150000.0, wage_level="IV"),
            # A denied row -- must never count toward main signals
            _row(fiscal_year=2026, case_status="DENIED", is_denied_or_withdrawn=True,
                 wage_offered=999999.0),
            # Stopped Co: filed in 2024 only
            _row(employer_raw="Stopped Co", employer_normalized="STOPPED",
                 fiscal_year=2024, wage_offered=110000.0),
            # Rival: Austin software, recent, for ranking
            _row(employer_raw="Rival Inc", employer_normalized="RIVAL",
                 fiscal_year=2026, wage_offered=160000.0, wage_level="IV"),
            _row(employer_raw="Rival Inc", employer_normalized="RIVAL",
                 fiscal_year=2026, wage_offered=180000.0, wage_level="IV"),
            # Dallas employer -- for metro filtering
            _row(employer_raw="Dallas Co", employer_normalized="DALLAS CO",
                 fiscal_year=2026, worksite_city="Dallas", wage_offered=130000.0),
        ]
    )


def test_signal1_total_excludes_denied(df):
    s = employer_signals(df, "ACME", "software_engineer")
    # 5 certified Acme rows; the DENIED one excluded
    assert s.total_certified_filings == 5
    assert s.denied_or_withdrawn_filings == 1


def test_signal2_role_bucket_specific(df):
    s = employer_signals(df, "ACME", "software_engineer")
    assert s.role_bucket_filings == 4  # 3 LCA sw + 1 PERM sw, not the QA row

    qa = employer_signals(df, "ACME", "qa_engineer")
    assert qa.role_bucket_filings == 1

    # The signal that justifies the product: heavy overall volume, zero in
    # the user's bucket.
    none_bucket = employer_signals(df, "ACME", "civil_engineer")
    assert none_bucket.total_certified_filings == 5
    assert none_bucket.role_bucket_filings == 0


def test_signal3_by_year_and_zero_filled(df):
    s = employer_signals(df, "ACME", "software_engineer")
    assert s.filings_by_fiscal_year == {2024: 1, 2025: 1, 2026: 3}
    assert s.stopped_filing is False


def test_signal3_stopped_filing_detected(df):
    s = employer_signals(df, "STOPPED", "software_engineer")
    assert s.filings_by_fiscal_year == {2024: 1, 2025: 0, 2026: 0}
    assert s.stopped_filing is True


def test_signal4_level_distribution_and_wage_range(df):
    s = employer_signals(df, "ACME", "software_engineer")
    assert s.wage_level_distribution == {"I": 1, "II": 1, "III": 1, "IV": 1}
    assert s.wage_min == 100000.0
    assert s.wage_max == 150000.0
    assert s.wage_median == 130000.0


def test_signal5_perm_presence(df):
    s = employer_signals(df, "ACME", "software_engineer")
    assert s.has_certified_perm is True
    assert s.perm_filings == 1
    assert s.lca_filings == 4

    # Heavy LCA, no PERM = no green card path there
    stopped = employer_signals(df, "STOPPED", "software_engineer")
    assert stopped.has_certified_perm is False


def test_signal5_uscis_reported_unavailable_not_zero(df):
    s = employer_signals(df, "ACME", "software_engineer")
    assert s.uscis_data_available is False
    assert s.uscis_approvals is None  # never 0 -- absent data isn't absence


def test_unknown_employer_returns_zeros_not_error(df):
    s = employer_signals(df, "NONEXISTENT", "software_engineer")
    assert s.total_certified_filings == 0
    assert s.role_bucket_filings == 0
    assert s.stopped_filing is False


def test_ranking_by_recent_volume(df):
    ranked = rank_employers_for_bucket_metro(df, "software_engineer", metro="Austin, TX")
    # Rival has 2 recent Austin sw filings, Acme 2 (1 LCA + 1 PERM in 2026)
    assert set(ranked["employer_normalized"]) == {"RIVAL", "ACME"}
    # Stopped Co filed only in 2024 -- excluded from the recent window
    assert "STOPPED" not in set(ranked["employer_normalized"])


def test_ranking_metro_filter(df):
    austin = rank_employers_for_bucket_metro(df, "software_engineer", metro="Austin, TX")
    assert "DALLAS CO" not in set(austin["employer_normalized"])

    dallas = rank_employers_for_bucket_metro(df, "software_engineer", metro="Dallas, TX")
    assert set(dallas["employer_normalized"]) == {"DALLAS CO"}


def test_ranking_empty_result_has_columns(df):
    empty = rank_employers_for_bucket_metro(df, "civil_engineer", metro="Austin, TX")
    assert empty.empty
    assert "employer_normalized" in empty.columns


def test_wage_stats_median_and_iqr(df):
    stats = wage_stats_for_bucket_metro(df, "software_engineer", metro="Austin, TX")
    # Austin sw certified wages: 100k,120k,140k,150k (Acme) + 160k,180k
    # (Rival) + 110k (Stopped) = 7 values. 999999 denied row excluded.
    assert stats.filing_count == 7
    assert stats.median == 140000.0
    assert stats.p25 is not None and stats.p75 is not None
    assert stats.p25 < stats.median < stats.p75


def test_wage_stats_excludes_denied_outlier(df):
    # The denied row carries a 999999 wage; it must not reach the stats.
    stats = wage_stats_for_bucket_metro(df, "software_engineer")
    assert stats.median != 999999.0
    assert stats.p75 != 999999.0


def test_wage_stats_empty_bucket(df):
    stats = wage_stats_for_bucket_metro(df, "civil_engineer")
    assert stats.filing_count == 0
    assert stats.median is None
