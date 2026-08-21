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
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

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
