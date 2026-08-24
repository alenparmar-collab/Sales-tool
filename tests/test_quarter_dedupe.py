"""The de-duplication has to produce the right answer whether OFLC's
quarterly releases are cumulative or incremental, because the first full
run showed the two programs may not behave the same way and guessing has
already been wrong once.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd  # noqa: E402


def _row(case, status="CERTIFIED", source="q1"):
    return {
        "case_number": case,
        "case_status": status,
        "is_denied_or_withdrawn": status in ("DENIED", "WITHDRAWN"),
        "source_file": source,
    }


def _dedupe(df):
    """Mirrors the pipeline's de-duplication: keep the newest release of
    each case, given frames concatenated oldest-first."""
    has_case = df["case_number"].notna() & (df["case_number"] != "")
    mask = df.loc[has_case].duplicated(subset=["case_number"], keep="last")
    dropped = int(mask.sum())
    return df.drop(index=df.loc[has_case].index[mask]).reset_index(drop=True), dropped


def test_incremental_releases_lose_nothing():
    # Disjoint quarters: every case survives, nothing is dropped.
    df = pd.DataFrame(
        [_row("A-1", source="q1"), _row("A-2", source="q2"),
         _row("A-3", source="q3"), _row("A-4", source="q4")]
    )
    out, dropped = _dedupe(df)
    assert dropped == 0
    assert len(out) == 4
    assert set(out["case_number"]) == {"A-1", "A-2", "A-3", "A-4"}


def test_cumulative_releases_collapse_to_the_true_count():
    # Cumulative: Q1 has 1 case, Q2 repeats it plus 1, Q3 repeats both plus
    # 1. The truth is 3 distinct cases, not 6 rows.
    df = pd.DataFrame(
        [
            _row("A-1", source="q1"),
            _row("A-1", source="q2"), _row("A-2", source="q2"),
            _row("A-1", source="q3"), _row("A-2", source="q3"), _row("A-3", source="q3"),
        ]
    )
    out, dropped = _dedupe(df)
    assert dropped == 3
    assert len(out) == 3
    assert set(out["case_number"]) == {"A-1", "A-2", "A-3"}


def test_newest_release_of_a_reissued_case_wins():
    # A case can be re-issued with a different final status. Frames arrive
    # oldest-first, so the later row is the one to keep -- otherwise a case
    # later certified would be reported using its earlier denial.
    df = pd.DataFrame(
        [_row("A-1", status="DENIED", source="q1"),
         _row("A-1", status="CERTIFIED", source="q3")]
    )
    out, dropped = _dedupe(df)
    assert dropped == 1
    assert len(out) == 1
    assert out.iloc[0]["case_status"] == "CERTIFIED"
    assert out.iloc[0]["source_file"] == "q3"
    assert bool(out.iloc[0]["is_denied_or_withdrawn"]) is False


def test_rows_without_case_numbers_are_never_dropped():
    # A blank case_number is not evidence of duplication.
    df = pd.DataFrame(
        [_row("", source="q1"), _row("", source="q2"), _row("A-1", source="q2")]
    )
    out, dropped = _dedupe(df)
    assert dropped == 0
    assert len(out) == 3
