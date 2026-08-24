"""Row-count reporting so a rerun can be sanity-checked at a glance."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import List

import pandas as pd

PROCESSED_DIR = Path(__file__).resolve().parent.parent / "data" / "processed"


def build_report(per_file_stats: List[dict], combined_df: pd.DataFrame) -> dict:
    by_year_program = (
        combined_df.groupby(["fiscal_year", "program"], dropna=False)
        .agg(
            total_rows=("employer_raw", "size"),
            main_counts=("is_denied_or_withdrawn", lambda s: int((~s).sum())),
            flagged_denied_withdrawn=("is_denied_or_withdrawn", lambda s: int(s.sum())),
        )
        .reset_index()
        .sort_values(["program", "fiscal_year"])
    )

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "per_file": per_file_stats,
        "by_fiscal_year_and_program": by_year_program.to_dict(orient="records"),
        "totals": {
            "total_rows": int(len(combined_df)),
            "main_counts": int((~combined_df["is_denied_or_withdrawn"]).sum()),
            "flagged_denied_withdrawn": int(combined_df["is_denied_or_withdrawn"].sum()),
        },
    }


def write_report(report: dict) -> Path:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = PROCESSED_DIR / f"run_report_{ts}.json"
    with open(path, "w") as f:
        json.dump(report, f, indent=2, default=str)
    latest = PROCESSED_DIR / "run_report_latest.json"
    with open(latest, "w") as f:
        json.dump(report, f, indent=2, default=str)
    return path


def print_report(report: dict) -> None:
    print("\n=== Row counts per source file ===")
    for row in report["per_file"]:
        print(
            f"  {row['source_file']:<45} raw_rows={row['raw_rows']:<8} "
            f"kept={row['kept_rows']:<8} dropped_unknown_status={row['dropped_unknown_status']}"
        )

    dupes = report.get("duplicate_case_numbers_dropped")
    if dupes is not None:
        total = report["totals"]["total_rows"] + dupes
        share = 100 * dupes / total if total else 0.0
        verdict = (
            "CUMULATIVE year-to-date -- overlap collapsed by de-duplication"
            if share > 10
            else "INCREMENTAL per quarter -- quarters are disjoint"
        )
        print("\n=== Overlap between quarterly releases ===")
        print(f"  duplicate case_numbers dropped: {dupes} of {total} ({share:.2f}%)")
        print(f"  -> OFLC releases look {verdict}")

    print("\n=== Row counts per fiscal year x program ===")
    for row in report["by_fiscal_year_and_program"]:
        print(
            f"  FY{row['fiscal_year']} {row['program']:<6} "
            f"total={row['total_rows']:<8} main={row['main_counts']:<8} "
            f"flagged_denied_withdrawn={row['flagged_denied_withdrawn']}"
        )

    t = report["totals"]
    print("\n=== Totals ===")
    print(f"  total_rows={t['total_rows']}  main_counts={t['main_counts']}  "
          f"flagged_denied_withdrawn={t['flagged_denied_withdrawn']}")
