#!/usr/bin/env python3
"""Demo: run the 10 test inputs from the build brief's Session 2 prompt
through the employer matcher and print what comes back.

IMPORTANT: this pipeline has never had real DOL data to build a real
top-500 alias map from (dol.gov is unreachable in the sandbox this was
built in -- see README.md). config/employer_aliases.yaml ships empty. So
this demo supplies a small SYNTHETIC alias map of realistic filer-name
variants for the 10 test companies, just so the matching logic itself
(exact alias hit, fuzzy hit, staffing-map short-circuit, honest no-match)
can be exercised end to end. Once run_pipeline.py has been run somewhere
with real internet access and src/employer_top_n.py has produced a real
top_500_employers.csv, replace this fixture by hand-building
config/employer_aliases.yaml for real and this script becomes unnecessary
(match_employer() with no arguments will use the real config files).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.employer_match import load_staffing_map, match_employer  # noqa: E402

# Synthetic, illustrative filer-name variants -- NOT pulled from a live
# DOL file. Realistic patterns based on how these employers commonly
# appear in public H-1B/PERM disclosure data.
DEMO_ALIAS_VARIANTS = {
    "Amazon": [
        "Amazon.com Services LLC",
        "Amazon Web Services Inc",
        "Amazon Development Center U.S. Inc",
        "Amazon Data Services Inc",
    ],
    "Google": ["Google LLC"],
    "Meta": ["Meta Platforms Inc", "Facebook Inc"],
    "JPMorgan Chase": ["JPMorgan Chase & Co", "JPMorgan Chase Bank NA", "J P Morgan Securities LLC"],
    "Capital One": ["Capital One Services LLC", "Capital One Bank USA NA", "Capital One Financial Corp"],
    "Walmart": ["Walmart Inc", "Wal-Mart Associates Inc", "Walmart Stores Inc"],
}


def build_demo_alias_map():
    from src.employer_normalize import normalize_employer_name

    alias_map = {}
    for canonical, variants in DEMO_ALIAS_VARIANTS.items():
        employer_id = canonical.lower().replace(" ", "_")
        for v in variants:
            norm = normalize_employer_name(v)
            if norm:
                alias_map[norm] = {"canonical": canonical, "employer_id": employer_id}
    return alias_map


TEST_INPUTS = [
    "Amazon",
    "Google",
    "Deloitte",
    "TCS",
    "Infosys",
    "Meta",
    "JPMorgan",
    "Capital One",
    "Cognizant",
    "Walmart",
]


def main():
    alias_map = build_demo_alias_map()
    staffing_map = load_staffing_map()  # this one IS the real shipped config

    print(f"{'input':<15} {'matched':<8} {'canonical':<28} {'score':<7} {'staffing/consulting':<20} candidates")
    print("-" * 110)
    for name in TEST_INPUTS:
        r = match_employer(name, alias_map=alias_map, staffing_map=staffing_map)
        if r.matched:
            print(
                f"{r.input_raw:<15} {'YES':<8} {str(r.canonical):<28} "
                f"{r.score:<7.1f} {str(r.is_staffing_or_consulting):<20}"
            )
        else:
            cand_str = ", ".join(f"{c.name} ({c.score:.0f})" for c in r.candidates)
            print(f"{r.input_raw:<15} {'NO':<8} {'-':<28} {'-':<7} {'-':<20} {cand_str}")


if __name__ == "__main__":
    main()
