import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import json  # noqa: E402

import pandas as pd  # noqa: E402
import pytest  # noqa: E402

from src.build_index import build_index, write_index  # noqa: E402


def _row(**kw):
    base = {
        "case_number": "C-1",
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
    base.update(kw)
    return base


@pytest.fixture
def df():
    rows = []
    # Acme: 10 software filings spread over 3 years, plus a PERM
    for i, fy in enumerate([2024] * 3 + [2025] * 3 + [2026] * 4):
        rows.append(_row(case_number=f"A-{i}", fiscal_year=fy, wage_offered=100000 + i * 5000))
    rows.append(_row(case_number="A-P", program="PERM", wage_offered=160000, wage_level=None))
    # Acme QA filings, so bucket separation is exercised
    for i in range(4):
        rows.append(
            _row(case_number=f"A-Q{i}", role_bucket="qa_engineer", wage_offered=90000, wage_level="I")
        )
    # A denied row that must never reach the index
    rows.append(
        _row(case_number="A-D", case_status="DENIED", is_denied_or_withdrawn=True,
             wage_offered=999999)
    )
    # Tiny employer below the floor
    rows.append(_row(case_number="T-1", employer_normalized="TINY", employer_raw="Tiny LLC"))
    return pd.DataFrame(rows)


def test_denied_rows_excluded(df):
    idx = build_index(df, min_filings=3)
    acme = next(e for e in idx["employers"] if e["n"] == "ACME")
    # 10 sw + 1 perm + 4 qa = 15 certified; the denied row is not counted.
    assert acme["t"] == 15
    for bucket in acme["b"].values():
        if "w" in bucket:
            assert bucket["w"][2] != 999999


def test_year_vector_aligns_with_meta(df):
    idx = build_index(df, min_filings=3)
    years = idx["meta"]["fiscal_years"]
    acme = next(e for e in idx["employers"] if e["n"] == "ACME")
    assert len(acme["y"]) == len(years)
    # 3 in FY2024, 3 in FY2025, and the rest (4 sw + 1 perm + 4 qa) in FY2026
    assert acme["y"][years.index(2024)] == 3
    assert acme["y"][years.index(2025)] == 3
    assert acme["y"][years.index(2026)] == 9


def test_buckets_are_separated(df):
    idx = build_index(df, min_filings=3)
    acme = next(e for e in idx["employers"] if e["n"] == "ACME")
    assert acme["b"]["software_engineer"]["t"] == 11  # 10 LCA + 1 PERM
    assert acme["b"]["qa_engineer"]["t"] == 4
    assert acme["b"]["qa_engineer"]["l"] == {"I": 4}


def test_perm_presence_recorded(df):
    idx = build_index(df, min_filings=3)
    acme = next(e for e in idx["employers"] if e["n"] == "ACME")
    assert acme["p"] == 1


def test_employers_below_floor_omitted_but_still_counted(df):
    idx = build_index(df, min_filings=3)
    names = {e["n"] for e in idx["employers"]}
    assert "TINY" not in names
    # The floor changes what has detail, not what the totals say.
    assert idx["meta"]["employers_total"] == 2
    assert idx["meta"]["employers_in_index"] == 1
    assert idx["meta"]["filings_counted"] == 16  # 15 Acme + 1 Tiny


def test_employers_sorted_by_volume(df):
    extra = pd.DataFrame(
        [_row(case_number=f"B-{i}", employer_normalized="BIGGER") for i in range(40)]
    )
    idx = build_index(pd.concat([df, extra], ignore_index=True), min_filings=3)
    assert idx["employers"][0]["n"] == "BIGGER"


def test_wage_stats_require_a_real_sample(df):
    # Only 11 Austin software filings here, under MIN_WAGE_SAMPLE, so no
    # percentile should be published rather than one built on 11 rows.
    idx = build_index(df, min_filings=3)
    assert "software_engineer|AUSTIN, TX" not in idx["wage_stats"]


def test_wage_stats_published_once_the_sample_is_large_enough():
    rows = [
        _row(case_number=f"W-{i}", employer_normalized=f"E{i % 5}", wage_offered=100000 + i * 1000)
        for i in range(40)
    ]
    idx = build_index(pd.DataFrame(rows), min_filings=3)
    key = "software_engineer|AUSTIN, TX"
    assert key in idx["wage_stats"]
    p25, median, p75, count = idx["wage_stats"][key]
    assert count == 40
    assert p25 < median < p75


def test_written_index_is_valid_compact_json(df, tmp_path):
    out = write_index(df, output_path=tmp_path / "index.json", min_filings=3)
    raw = out.read_text()
    parsed = json.loads(raw)

    assert parsed["meta"]["source_url"].startswith("https://www.dol.gov")
    assert len(parsed["employers"]) == 1

    # Written with compact separators -- every byte is bandwidth on a page
    # that ships this to each visitor.
    assert len(raw) < len(json.dumps(parsed))


ALIAS_FIXTURE = {
    "AMAZON COM": {"canonical": "Amazon", "employer_id": "amazon"},
    "AMAZON WEB": {"canonical": "Amazon", "employer_id": "amazon"},
    "AMAZON DATA": {"canonical": "Amazon", "employer_id": "amazon"},
    "COGNIZANT TECHNOLOGY": {
        "canonical": "Cognizant", "employer_id": "cognizant",
        "is_staffing_or_consulting": True,
    },
}


def _multi_entity_df():
    rows = []
    for ent in ["AMAZON COM", "AMAZON WEB", "AMAZON DATA"]:
        for i in range(5):
            rows.append(_row(case_number=f"{ent}-{i}", employer_normalized=ent,
                             employer_raw=ent, fiscal_year=[2024, 2025, 2026][i % 3]))
    for i in range(5):
        rows.append(_row(case_number=f"COG-{i}", employer_normalized="COGNIZANT TECHNOLOGY",
                         employer_raw="Cognizant Technology Solutions"))
    return pd.DataFrame(rows)


def test_alias_map_merges_filing_entities():
    # Without this the curated alias map has no effect on the shipped data:
    # AMAZON COM / WEB / DATA stay three rows and every Amazon count is a
    # third of the truth.
    df = _multi_entity_df()
    idx = build_index(df, min_filings=3, alias_map=ALIAS_FIXTURE, staffing_map={})
    names = {e["n"] for e in idx["employers"]}
    assert "Amazon" in names
    assert "AMAZON COM" not in names

    amazon = next(e for e in idx["employers"] if e["n"] == "Amazon")
    assert amazon["t"] == 15  # 3 entities x 5 filings, counted once each
    assert sum(amazon["y"]) == 15


def test_merged_entities_are_named_in_the_index():
    # A user seeing one combined number should be able to see what it spans.
    idx = build_index(_multi_entity_df(), min_filings=3,
                      alias_map=ALIAS_FIXTURE, staffing_map={})
    amazon = next(e for e in idx["employers"] if e["n"] == "Amazon")
    assert set(amazon["e"]) == {"AMAZON COM", "AMAZON WEB", "AMAZON DATA"}


def test_staffing_flag_comes_from_curation_not_name_guessing():
    idx = build_index(_multi_entity_df(), min_filings=3,
                      alias_map=ALIAS_FIXTURE, staffing_map={})
    cog = next(e for e in idx["employers"] if e["n"] == "Cognizant")
    assert cog.get("s") == 1
    amazon = next(e for e in idx["employers"] if e["n"] == "Amazon")
    assert "s" not in amazon


def test_empty_alias_map_degrades_to_unmerged():
    # An empty or partial map must not break the build -- it just leaves
    # entities separate, which is the state before curation.
    idx = build_index(_multi_entity_df(), min_filings=3, alias_map={}, staffing_map={})
    names = {e["n"] for e in idx["employers"]}
    assert "AMAZON COM" in names and "AMAZON WEB" in names
    assert "Amazon" not in names
