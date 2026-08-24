#!/usr/bin/env python3
"""CLI entrypoint. Rerun this each quarter after DOL publishes a new release.

Usage:
    python run_pipeline.py
    python run_pipeline.py --force-download
    python run_pipeline.py --lca-years 3 --perm-years 2
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.discover_sources import PERFORMANCE_PAGE, SourceDiscoveryError  # noqa: E402
from src.columns import ColumnResolutionError  # noqa: E402
from src.download import DownloadError  # noqa: E402
from src.pipeline import run  # noqa: E402


def discover_only(page_url: str, lca_years: int, perm_years: int) -> int:
    """Report what discovery finds without downloading it.

    HEAD each candidate URL for its size so the real run can be sized in
    advance -- these files are large enough that running out of disk or
    memory mid-way is a real risk worth measuring first.
    """
    import requests

    from src.discover_sources import USER_AGENT, get_sources

    sources = get_sources(page_url=page_url, lca_years=lca_years, perm_years=perm_years)

    data_files = [s for s in sources if s.kind != "LAYOUT"]
    layouts = [s for s in sources if s.kind == "LAYOUT"]

    total_bytes = 0
    unknown_sizes = 0

    print(f"\n=== Discovery against {page_url} ===")
    print(f"Data files selected: {len(data_files)}   Record layouts: {len(layouts)}\n")

    for s in sorted(data_files, key=lambda x: (x.kind, x.fiscal_year or 0)):
        size_str = "unknown"
        try:
            r = requests.head(
                s.url, timeout=30, allow_redirects=True, headers={"User-Agent": USER_AGENT}
            )
            length = r.headers.get("Content-Length")
            if length:
                size = int(length)
                total_bytes += size
                size_str = f"{size / (1024 ** 2):.1f} MB"
            else:
                unknown_sizes += 1
        except requests.exceptions.RequestException as e:
            size_str = f"HEAD failed: {e}"
            unknown_sizes += 1

        fy = f"FY{s.fiscal_year}" if s.fiscal_year else "FY?"
        print(f"  [{s.kind:<13}] {fy:<7} {size_str:>14}   {s.url}")

    print("\n  Record layout documents:")
    for s in layouts:
        print(f"    {s.url}")

    print(f"\n=== Total known download size: {total_bytes / (1024 ** 3):.2f} GB ===")
    if unknown_sizes:
        print(f"    ({unknown_sizes} file(s) did not report a size)")

    kinds = {s.kind for s in data_files}
    print("\nSanity checks:")
    print(f"  LCA files found:          {sum(1 for s in data_files if s.kind == 'LCA')}")
    print(f"  PERM legacy files found:  {sum(1 for s in data_files if s.kind == 'PERM_LEGACY')}")
    print(f"  PERM revised files found: {sum(1 for s in data_files if s.kind == 'PERM_REVISED')}")
    if "PERM_REVISED" not in kinds:
        print(
            "\n  NOTE: no file was classified PERM_REVISED. Either OFLC hasn't split\n"
            "  the file the way the brief describes, or the classifier's keywords\n"
            "  don't match how they labelled it. Check the URLs above by eye."
        )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--page-url", default=PERFORMANCE_PAGE)
    parser.add_argument("--lca-years", type=int, default=3)
    parser.add_argument("--perm-years", type=int, default=2)
    parser.add_argument(
        "--force-download",
        action="store_true",
        help="Re-download files even if already present in data/raw/.",
    )
    parser.add_argument(
        "--discover-only",
        action="store_true",
        help="Scrape the DOL page, report which files would be pulled and how "
        "big they are, then stop. Downloads nothing. Use this to sanity-check "
        "discovery and size the real run before committing to it.",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    if args.discover_only:
        try:
            return discover_only(
                page_url=args.page_url,
                lca_years=args.lca_years,
                perm_years=args.perm_years,
            )
        except SourceDiscoveryError as e:
            print(f"\nSOURCE DISCOVERY FAILED: {e}", file=sys.stderr)
            return 2

    try:
        run(
            page_url=args.page_url,
            lca_years=args.lca_years,
            perm_years=args.perm_years,
            force_download=args.force_download,
        )
    except SourceDiscoveryError as e:
        print(f"\nSOURCE DISCOVERY FAILED: {e}", file=sys.stderr)
        return 2
    except ColumnResolutionError as e:
        print(f"\nCOLUMN MAPPING FAILED: {e}", file=sys.stderr)
        return 3
    except DownloadError as e:
        print(f"\nDOWNLOAD FAILED: {e}", file=sys.stderr)
        return 4

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
