import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd  # noqa: E402

from src.normalize import normalize_file  # noqa: E402


def test_normalize_lca_end_to_end():
    raw = pd.DataFrame(
        [
            {
                "CASE_STATUS": "Certified",
                "DECISION_DATE": "2025-11-15",
                "EMPLOYER_NAME": " Amazon.com Services LLC ",
                "JOB_TITLE": "Software Engineer II",
                "SOC_CODE": "15-1252",
                "WORKSITE_CITY": "Seattle",
                "WORKSITE_STATE": "WA",
                "WAGE_RATE_OF_PAY_FROM": "50",
                "WAGE_UNIT_OF_PAY": "Hour",
                "PW_WAGE_LEVEL": "II",
                "FULL_TIME_POSITION": "Y",
            },
            {
                "CASE_STATUS": "Certified - Withdrawn",
                "DECISION_DATE": "2024-05-01",
                "EMPLOYER_NAME": "Acme Corp",
                "JOB_TITLE": "Data Engineer",
                "SOC_CODE": "15-1243",
                "WORKSITE_CITY": "Austin",
                "WORKSITE_STATE": "TX",
                "WAGE_RATE_OF_PAY_FROM": "120000",
                "WAGE_UNIT_OF_PAY": "Year",
                "PW_WAGE_LEVEL": "III",
                "FULL_TIME_POSITION": "N",
            },
            {
                "CASE_STATUS": "Denied",
                "DECISION_DATE": "2025-01-10",
                "EMPLOYER_NAME": "Beta LLC",
                "JOB_TITLE": "QA Analyst",
                "SOC_CODE": "15-1253",
                "WORKSITE_CITY": "Dallas",
                "WORKSITE_STATE": "TX",
                "WAGE_RATE_OF_PAY_FROM": "40",
                "WAGE_UNIT_OF_PAY": "Hour",
                "PW_WAGE_LEVEL": "I",
                "FULL_TIME_POSITION": "Y",
            },
            {
                # unrecognized status -- should be dropped, not silently kept
                "CASE_STATUS": "Pending",
                "DECISION_DATE": "2025-01-10",
                "EMPLOYER_NAME": "Gamma Inc",
                "JOB_TITLE": "Analyst",
                "SOC_CODE": "13-1111",
                "WORKSITE_CITY": "Denver",
                "WORKSITE_STATE": "CO",
                "WAGE_RATE_OF_PAY_FROM": "40",
                "WAGE_UNIT_OF_PAY": "Hour",
                "PW_WAGE_LEVEL": "I",
                "FULL_TIME_POSITION": "Y",
            },
        ]
    )

    out, dropped = normalize_file(raw, file_kind="LCA", program="LCA", source_label="fake_lca.xlsx")

    assert dropped == 1
    assert len(out) == 3

    row0 = out.iloc[0]
    assert row0["employer_raw"] == "Amazon.com Services LLC"
    assert row0["case_status"] == "CERTIFIED"
    assert row0["fiscal_year"] == 2026  # Nov 2025 -> FY2026
    assert row0["wage_offered"] == 50 * 2080
    assert bool(row0["full_time_flag"]) is True
    assert bool(row0["is_denied_or_withdrawn"]) is False

    row1 = out.iloc[1]
    assert row1["case_status"] == "CERTIFIED-WITHDRAWN"
    assert row1["fiscal_year"] == 2024  # May 2024 -> FY2024
    assert row1["wage_offered"] == 120000
    assert bool(row1["is_denied_or_withdrawn"]) is False

    row2 = out.iloc[2]
    assert row2["case_status"] == "DENIED"
    assert bool(row2["is_denied_or_withdrawn"]) is True

    # Main-counts filter should exclude the denied row.
    main_counts = out[~out["is_denied_or_withdrawn"]]
    assert len(main_counts) == 2
