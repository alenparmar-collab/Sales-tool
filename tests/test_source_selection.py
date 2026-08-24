"""Selection logic, pinned against the real file list DOL actually serves
(observed in a discovery run on 2026-08-24)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.discover_sources import (  # noqa: E402
    SourceFile,
    _classify,
    _extract_quarter,
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


def test_unquartered_file_sorts_last_within_its_year():
    # A file with no quarter marker is treated as the most recent release
    # of the cases it holds, so it must sort after Q1..Q4 -- de-duplication
    # keeps the last occurrence.
    links = [
        _f("PERM_Disclosure_Data_FY2026_Q3.xlsx", "PERM_LEGACY", 2026, 3),
        _f("PERM_Disclosure_Data_FY2026.xlsx", "PERM_LEGACY", 2026, None),
        _f("LCA_Disclosure_Data_FY2026_Q3.xlsx", "LCA", 2026, 3),
    ]
    selected = select_sources(links, lca_years=3, perm_years=2)
    perm = [s for s in selected if s.kind == "PERM_LEGACY"]
    assert [s.quarter for s in perm] == [3, None]


def test_select_sources_keeps_every_quarter():
    # Every quarterly release in the window is ingested; correctness comes
    # from de-duplicating case_number afterwards rather than from a guess
    # about whether the releases are cumulative. The first full run showed
    # keeping only Q4 lost ~80% of FY2024 and FY2025 LCA rows.
    selected = select_sources(REAL_LINKS, lca_years=3, perm_years=2)
    data = [s for s in selected if s.kind != "LAYOUT"]

    assert sum(1 for s in data if s.kind == "LCA") == 9  # 4 + 4 + 1
    lca_2025 = sorted(s.quarter for s in data if s.kind == "LCA" and s.fiscal_year == 2025)
    assert lca_2025 == [1, 2, 3, 4]


def test_perm_year_window_spans_both_kinds():
    # FY2024's revised-form file is outside a two-year PERM window and has
    # no legacy counterpart in the listing; including it produced a
    # spuriously small FY2024 PERM total in the run report.
    selected = select_sources(REAL_LINKS, lca_years=3, perm_years=2)
    perm = [s for s in selected if s.kind in ("PERM_LEGACY", "PERM_REVISED")]

    assert {s.fiscal_year for s in perm} == {2025, 2026}
    assert all(s.fiscal_year != 2024 for s in perm)


def test_selected_files_ordered_oldest_quarter_first():
    # De-duplication keeps the last occurrence, so ordering decides which
    # release of a re-issued case survives.
    selected = select_sources(REAL_LINKS, lca_years=3, perm_years=2)
    lca = [s for s in selected if s.kind == "LCA"]
    keys = [(s.fiscal_year, s.quarter or 99) for s in lca]
    assert keys == sorted(keys)


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
