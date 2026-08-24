"""Selection logic, pinned against the real file list DOL actually serves
(observed in a discovery run on 2026-08-24)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.discover_sources import (  # noqa: E402
    SourceFile,
    _classify,
    _extract_quarter,
    _latest_per_fiscal_year,
    select_sources,
)

BASE = "https://www.dol.gov/sites/dolgov/files/ETA/oflc/pdfs/"


def _f(name, kind, fy, q):
    return SourceFile(url=BASE + name, kind=kind, fiscal_year=fy, link_text=name, quarter=q)


# Exactly what discovery returned against the live page.
REAL_LINKS = [
    _f("LCA_Disclosure_Data_FY2024_Q1.xlsx", "LCA", 2024, 1),
    _f("LCA_Disclosure_Data_FY2024_Q2.xlsx", "LCA", 2024, 2),
    _f("LCA_Disclosure_Data_FY2024_Q3.xlsx", "LCA", 2024, 3),
    _f("LCA_Disclosure_Data_FY2024_Q4.xlsx", "LCA", 2024, 4),
    _f("LCA_Disclosure_Data_FY2025_Q1.xlsx", "LCA", 2025, 1),
    _f("LCA_Disclosure_Data_FY2025_Q2.xlsx", "LCA", 2025, 2),
    _f("LCA_Disclosure_Data_FY2025_Q3.xlsx", "LCA", 2025, 3),
    _f("LCA_Disclosure_Data_FY2025_Q4.xlsx", "LCA", 2025, 4),
    _f("LCA_Disclosure_Data_FY2026_Q3.xlsx", "LCA", 2026, 3),
    _f("PERM_Disclosure_Data_FY2025_Q4.xlsx", "PERM_LEGACY", 2025, 4),
    _f("PERM_Disclosure_Data_FY2026_Q3.xlsx", "PERM_LEGACY", 2026, 3),
    _f("PERM_Disclosure_Data_New_Form_FY2024_Q4.xlsx", "PERM_REVISED", 2024, 4),
]


def test_quarter_extraction():
    assert _extract_quarter("LCA_Disclosure_Data_FY2025_Q3.xlsx", "") == 3
    assert _extract_quarter("PERM_Disclosure_Data_FY2026_Q1.xlsx", "") == 1
    assert _extract_quarter("PERM_Record_Layout_FY2021.pdf", "") is None


def test_only_latest_quarter_per_fiscal_year_survives():
    kept = _latest_per_fiscal_year([f for f in REAL_LINKS if f.kind == "LCA"])
    by_fy = {f.fiscal_year: f for f in kept}

    # One file per year, not four -- the quarterly releases are cumulative.
    assert len(kept) == 3
    assert by_fy[2024].quarter == 4
    assert by_fy[2025].quarter == 4
    assert by_fy[2026].quarter == 3  # FY2026 is still in progress


def test_unquartered_file_beats_quartered_one():
    # A file with no quarter marker is treated as the consolidated annual
    # release and should win over Q1..Q4 of the same year.
    files = [
        _f("PERM_Disclosure_Data_FY2021_Q3.xlsx", "PERM_LEGACY", 2021, 3),
        _f("PERM_Disclosure_Data_FY2021.xlsx", "PERM_LEGACY", 2021, None),
    ]
    kept = _latest_per_fiscal_year(files)
    assert len(kept) == 1
    assert kept[0].quarter is None


def test_select_sources_against_real_listing():
    selected = select_sources(REAL_LINKS, lca_years=3, perm_years=2)
    data = [s for s in selected if s.kind != "LAYOUT"]

    # Was 12 files before the fix (and would have multi-counted); now 6:
    # 3 LCA + 2 PERM legacy + 1 PERM revised.
    assert len(data) == 6
    assert sum(1 for s in data if s.kind == "LCA") == 3
    assert sum(1 for s in data if s.kind == "PERM_LEGACY") == 2
    assert sum(1 for s in data if s.kind == "PERM_REVISED") == 1


def test_layout_classifier_excludes_other_programs():
    # The brief excludes H-2A, H-2B and CW-1; DOL lists their layouts on the
    # same page, and pulling them was pure noise.
    assert _classify(BASE + "H-2B_Record_Layout_FY2024_Q4.pdf", "") is None
    assert _classify(BASE + "H-2A_Record_Layout_FY2025_Q4.pdf", "") is None
    assert _classify(BASE + "CW-1_Record_Layout_FY2021.pdf", "") is None
    assert _classify(BASE + "PW_Record_Layout_FY2020.pdf", "") is None

    assert _classify(BASE + "LCA_Record_Layout_FY2026_Q3.pdf", "") == "LAYOUT"
    assert _classify(BASE + "PERM_Record_Layout_FY2025_Q4.pdf", "") == "LAYOUT"
    assert _classify(BASE + "PERM_New_Form_Record_Layout_FY2024_Q4.pdf", "") == "LAYOUT"


def test_new_form_is_classified_revised():
    assert (
        _classify(BASE + "PERM_Disclosure_Data_New_Form_FY2024_Q4.xlsx", "") == "PERM_REVISED"
    )
