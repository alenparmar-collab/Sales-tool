"""End-to-end smoke test: real .xlsx files on disk -> pipeline.run() ->
parquet/csv output + report, with discovery/download stubbed out (no
network in this sandbox). Proves the read -> normalize -> combine -> write
-> report path actually works, independent of whether dol.gov is reachable.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd  # noqa: E402

from src import pipeline  # noqa: E402
from src.discover_sources import SourceFile  # noqa: E402


def _write_lca_xlsx(path: Path):
    df = pd.DataFrame(
        [
            {
                "CASE_STATUS": "Certified",
                "DECISION_DATE": "2025-11-15",
                "EMPLOYER_NAME": "Amazon.com Services LLC",
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
        ]
    )
    df.to_excel(path, index=False, engine="openpyxl")


def _write_perm_xlsx(path: Path):
    df = pd.DataFrame(
        [
            {
                "CASE_STATUS": "Certified",
                "DECISION_DATE": "2025-02-20",
                "EMPLOYER_NAME": "Acme Corp",
                "JOB_INFO_JOB_TITLE": "Data Scientist",
                "PW_SOC_CODE": "15-2051",
                "JOB_INFO_WORK_CITY": "Chicago",
                "JOB_INFO_WORK_STATE": "IL",
                "WAGE_OFFER_FROM_9089": "130000",
                "WAGE_OFFER_UNIT_OF_PAY_9089": "Year",
                "PW_LEVEL_9089": "IV",
                "FULL_TIME_POSITION_9089": "Y",
            },
        ]
    )
    df.to_excel(path, index=False, engine="openpyxl")


def test_pipeline_run_end_to_end(tmp_path, monkeypatch):
    lca_path = tmp_path / "LCA_Disclosure_Data_FY2026_Q3.xlsx"
    perm_path = tmp_path / "PERM_Disclosure_Data_FY2026_Q3.xlsx"
    _write_lca_xlsx(lca_path)
    _write_perm_xlsx(perm_path)

    fake_sources = [
        SourceFile(url="http://example.test/lca.xlsx", kind="LCA", fiscal_year=2026, link_text="LCA"),
        SourceFile(
            url="http://example.test/perm.xlsx", kind="PERM_LEGACY", fiscal_year=2026, link_text="PERM"
        ),
    ]

    def fake_get_sources(**kwargs):
        return fake_sources

    def fake_download_sources(sources, force=False):
        return [
            {
                "url": "http://example.test/lca.xlsx",
                "kind": "LCA",
                "fiscal_year": 2026,
                "link_text": "LCA",
                "local_path": str(lca_path),
            },
            {
                "url": "http://example.test/perm.xlsx",
                "kind": "PERM_LEGACY",
                "fiscal_year": 2026,
                "link_text": "PERM",
                "local_path": str(perm_path),
            },
        ]

    monkeypatch.setattr(pipeline, "get_sources", fake_get_sources)
    monkeypatch.setattr(pipeline, "download_sources", fake_download_sources)
    monkeypatch.setattr(pipeline, "PROCESSED_DIR", tmp_path / "processed")
    monkeypatch.setattr(pipeline, "OUTPUT_PARQUET", tmp_path / "processed" / "dol_filings.parquet")
    monkeypatch.setattr(pipeline, "OUTPUT_CSV", tmp_path / "processed" / "dol_filings.csv")
    monkeypatch.setattr("src.report.PROCESSED_DIR", tmp_path / "processed")
    # pipeline.run() writes the published site index too. Without this the
    # test overwrites web/data/index.json -- the file the live site serves.
    monkeypatch.setattr("src.build_index.DEFAULT_OUTPUT", tmp_path / "index.json")

    report = pipeline.run()

    assert report["totals"]["total_rows"] == 3
    assert report["totals"]["main_counts"] == 2
    assert report["totals"]["flagged_denied_withdrawn"] == 1
    assert (tmp_path / "processed" / "dol_filings.parquet").exists()
    assert (tmp_path / "processed" / "dol_filings.csv").exists()

    combined = pd.read_parquet(tmp_path / "processed" / "dol_filings.parquet")
    assert set(combined["program"].unique()) == {"LCA", "PERM"}
    assert combined.loc[combined["program"] == "PERM", "wage_offered"].iloc[0] == 130000
