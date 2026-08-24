import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd  # noqa: E402

from src.unmatched_titles import top_unmatched_titles, write_top_unmatched_titles  # noqa: E402


def test_only_other_rows_counted_and_ranked():
    df = pd.DataFrame(
        [
            {"job_title_raw": "Widget Wrangler", "soc_code": "15-1299", "role_bucket": "other"},
            {"job_title_raw": "Widget Wrangler", "soc_code": "15-1299", "role_bucket": "other"},
            {"job_title_raw": "Thing Doer", "soc_code": "13-1111", "role_bucket": "other"},
            {"job_title_raw": "Software Engineer", "soc_code": "15-1252", "role_bucket": "software_engineer"},
        ]
    )
    top = top_unmatched_titles(df, top_n=10)

    assert len(top) == 2  # the classified row is excluded
    assert top.iloc[0]["job_title_raw"] == "Widget Wrangler"
    assert top.iloc[0]["filing_count"] == 2
    assert "15-1299" in top.iloc[0]["sample_soc_codes"]


def test_respects_top_n():
    df = pd.DataFrame(
        [{"job_title_raw": f"Title {i}", "soc_code": None, "role_bucket": "other"} for i in range(20)]
    )
    assert len(top_unmatched_titles(df, top_n=5)) == 5


def test_empty_when_nothing_unmatched():
    df = pd.DataFrame(
        [{"job_title_raw": "Software Engineer", "soc_code": "15-1252", "role_bucket": "software_engineer"}]
    )
    assert top_unmatched_titles(df).empty


def test_writes_csv(tmp_path):
    df = pd.DataFrame(
        [{"job_title_raw": "Widget Wrangler", "soc_code": "15-1299", "role_bucket": "other"}]
    )
    out_path = tmp_path / "unmatched.csv"
    write_top_unmatched_titles(df, output_path=out_path)
    assert out_path.exists()
    assert "Widget Wrangler" in out_path.read_text()
