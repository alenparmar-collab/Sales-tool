"""Discover current LCA / PERM disclosure file links from the DOL OFLC
performance data page.

This is what makes the pipeline rerunnable each quarter without editing
code: DOL updates https://www.dol.gov/agencies/eta/foreign-labor/performance
in place each release, replacing filenames (new quarter labels, sometimes
new URL paths). Rather than hardcode a URL, we scrape the page for every
link ending in .xlsx/.xls/.pdf and classify by filename/link-text keywords.

If DOL restructures the page enough that this scrape stops finding the
expected files, it fails loudly (see PERFORMANCE_PAGE / SourceDiscoveryError)
rather than silently returning nothing -- at that point, list the files by
hand in config/sources_override.yaml, which always takes priority over
discovery.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional
from urllib.parse import urljoin

import requests
import yaml
from bs4 import BeautifulSoup

PERFORMANCE_PAGE = "https://www.dol.gov/agencies/eta/foreign-labor/performance"
REQUEST_TIMEOUT = 60
USER_AGENT = "Mozilla/5.0 (compatible; MediNext-DOL-Pipeline/1.0; +https://medinextglobal.com)"
OVERRIDE_PATH = Path(__file__).resolve().parent.parent / "config" / "sources_override.yaml"

FY_PATTERN = re.compile(r"FY\s?(20\d{2})", re.IGNORECASE)
QUARTER_PATTERN = re.compile(r"[_\-\s]Q([1-4])\b", re.IGNORECASE)


class SourceDiscoveryError(RuntimeError):
    pass


@dataclass
class SourceFile:
    url: str
    kind: str  # LCA, PERM_LEGACY, PERM_REVISED, LAYOUT
    fiscal_year: Optional[int]
    link_text: str
    quarter: Optional[int] = None


def _classify(url: str, link_text: str) -> Optional[str]:
    haystack = f"{url} {link_text}".upper()

    if haystack.endswith(".PDF") or ".PDF" in haystack.split("?")[0]:
        if "RECORD_LAYOUT" not in haystack and "RECORD LAYOUT" not in haystack:
            return None
        # Only LCA and PERM layouts are relevant. DOL publishes layouts for
        # every program on the same page (H-2A, H-2B, CW-1, PW), and the
        # brief explicitly excludes those -- wrong programs, wrong buyer.
        if "PERM" in haystack or "LCA" in haystack:
            return "LAYOUT"
        return None

    is_lca = "LCA" in haystack and "DISCLOSURE" in haystack
    is_perm = "PERM" in haystack and "DISCLOSURE" in haystack

    if is_lca:
        return "LCA"
    if is_perm:
        is_revised = any(
            token in haystack for token in ["REVISED", "9089R", "NEW FORM", "NEW_FORM"]
        )
        return "PERM_REVISED" if is_revised else "PERM_LEGACY"
    return None


def _extract_fiscal_year(url: str, link_text: str) -> Optional[int]:
    for haystack in (link_text, url):
        m = FY_PATTERN.search(haystack)
        if m:
            return int(m.group(1))
    return None


def _extract_quarter(url: str, link_text: str) -> Optional[int]:
    """Quarter number from a filename like ..._FY2025_Q3.xlsx.

    Returns None when a file carries no quarter marker. Such a file sorts
    last within its fiscal year, so de-duplication treats it as the most
    recent release of the cases it contains.
    """
    for haystack in (link_text, url):
        m = QUARTER_PATTERN.search(haystack)
        if m:
            return int(m.group(1))
    return None


def fetch_page_links(page_url: str = PERFORMANCE_PAGE) -> List[SourceFile]:
    try:
        resp = requests.get(page_url, timeout=REQUEST_TIMEOUT, headers={"User-Agent": USER_AGENT})
        resp.raise_for_status()
    except requests.exceptions.RequestException as e:
        raise SourceDiscoveryError(
            f"Could not reach {page_url}: {e}\n"
            "If this is a network/firewall issue in your environment, either "
            "run the pipeline somewhere with normal internet access, or "
            "download the files by hand and list them in "
            "config/sources_override.yaml (which skips this fetch entirely)."
        ) from e
    soup = BeautifulSoup(resp.text, "html.parser")

    found: List[SourceFile] = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if not re.search(r"\.(xlsx|xls|pdf)(\?.*)?$", href, re.IGNORECASE):
            continue
        full_url = urljoin(page_url, href)
        link_text = a.get_text(strip=True) or ""
        kind = _classify(full_url, link_text)
        if kind is None:
            continue
        fy = _extract_fiscal_year(full_url, link_text)
        q = _extract_quarter(full_url, link_text)
        found.append(
            SourceFile(url=full_url, kind=kind, fiscal_year=fy, link_text=link_text, quarter=q)
        )

    if not found:
        raise SourceDiscoveryError(
            f"No LCA/PERM disclosure or layout links found on {page_url}. "
            "DOL likely changed the page structure -- inspect the page by hand "
            "and either fix the classification rules in discover_sources.py or "
            "list files manually in config/sources_override.yaml."
        )
    return found


def select_sources(
    all_links: List[SourceFile],
    lca_years: int = 3,
    perm_years: int = 2,
) -> List[SourceFile]:
    """Pick the N most recent distinct fiscal years for LCA, and PERM
    (legacy + revised, whichever exist) for the M most recent fiscal years.
    Layout PDFs are always kept (for reference / manual verification).
    """
    layouts = [f for f in all_links if f.kind == "LAYOUT"]

    def top_fiscal_years(kind: str, n: int) -> set:
        years = sorted(
            {f.fiscal_year for f in all_links if f.kind == kind and f.fiscal_year is not None},
            reverse=True,
        )
        return set(years[:n])

    lca_keep_years = top_fiscal_years("LCA", lca_years)

    # PERM's two file kinds are two halves of one program, so the year
    # window is computed across both together. Computing it per kind pulled
    # in an orphan FY2024 revised-form file -- the only year that kind
    # existed -- with no legacy counterpart alongside it, which showed up in
    # the run report as a spuriously small FY2024 PERM total.
    perm_years_pool = sorted(
        {
            f.fiscal_year
            for f in all_links
            if f.kind in ("PERM_LEGACY", "PERM_REVISED") and f.fiscal_year is not None
        },
        reverse=True,
    )
    perm_keep_years = set(perm_years_pool[:perm_years])

    # EVERY quarterly release in the window is taken, not just the newest.
    #
    # An earlier version kept only the latest quarter per fiscal year, on
    # the basis that OFLC's releases are cumulative year-to-date. The first
    # full run disproved that for LCA: FY2024 and FY2025 came back at ~117k
    # rows each against ~437k for FY2026, when real LCA volume is roughly
    # 600-750k a year. The Q4 file is evidently one quarter, not the year.
    # PERM's totals over the same window looked like full years, so the two
    # programs may not even behave alike.
    #
    # Rather than guess a third time, the pipeline now ingests every quarter
    # and de-duplicates on case_number, keeping the newest release of each
    # case. That is correct under BOTH readings: if the files are
    # incremental the quarters are disjoint and nothing is dropped; if they
    # are cumulative the overlap collapses. The duplicate count in the run
    # report then says which is true, as a measurement rather than an
    # assumption.
    data_files = [f for f in all_links if f.kind == "LCA" and f.fiscal_year in lca_keep_years]
    data_files += [
        f
        for f in all_links
        if f.kind in ("PERM_LEGACY", "PERM_REVISED") and f.fiscal_year in perm_keep_years
    ]

    selected = sorted(
        data_files, key=lambda f: (f.kind, f.fiscal_year or 0, f.quarter if f.quarter else 99)
    )
    selected += layouts

    if not any(f.kind == "LCA" for f in selected):
        raise SourceDiscoveryError("Discovery found the page but no LCA files matched.")
    if not any(f.kind in ("PERM_LEGACY", "PERM_REVISED") for f in selected):
        raise SourceDiscoveryError("Discovery found the page but no PERM files matched.")

    return selected


def load_manual_overrides(path: Path = OVERRIDE_PATH) -> List[SourceFile]:
    if not path.exists():
        return []
    with open(path, "r") as f:
        data = yaml.safe_load(f) or {}
    entries = data.get("files") or []
    return [
        SourceFile(
            url=e["url"],
            kind=e["kind"],
            fiscal_year=e.get("fiscal_year"),
            link_text=e.get("link_text", "manual override"),
            quarter=e.get("quarter"),
        )
        for e in entries
    ]


def get_sources(
    page_url: str = PERFORMANCE_PAGE,
    lca_years: int = 3,
    perm_years: int = 2,
    override_path: Path = OVERRIDE_PATH,
) -> List[SourceFile]:
    """Manual overrides always win. If config/sources_override.yaml lists
    any files, those are used as-is (no scrape). Otherwise scrape the DOL
    page and auto-select the most recent fiscal years."""
    overrides = load_manual_overrides(override_path)
    if overrides:
        return overrides

    all_links = fetch_page_links(page_url)
    return select_sources(all_links, lca_years=lca_years, perm_years=perm_years)
