"""Match free-text employer input (what a user types) against the known
employer universe: the hand-built alias map first, then the staffing/
consulting abbreviation map, then fuzzy matching with a confidence
threshold. Below threshold, return no match plus the closest candidates --
never guess. A wrong confident answer ("this company doesn't sponsor" when
it does) is worse than admitting uncertainty.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

import yaml
from rapidfuzz import fuzz, process

from .employer_normalize import normalize_employer_name

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"
EMPLOYER_ALIAS_PATH = CONFIG_DIR / "employer_aliases.yaml"
STAFFING_PATH = CONFIG_DIR / "staffing_consulting_firms.yaml"

# token_set_ratio is 0-100; this is deliberately strict (brief: "high
# threshold... when the score is below threshold, do not guess").
DEFAULT_THRESHOLD = 90.0


@dataclass
class Candidate:
    name: str
    score: float


@dataclass
class MatchResult:
    input_raw: str
    matched: bool
    canonical: Optional[str] = None
    employer_id: Optional[str] = None
    score: Optional[float] = None
    is_staffing_or_consulting: bool = False
    candidates: List[Candidate] = field(default_factory=list)


def load_staffing_map(path: Path = STAFFING_PATH) -> Dict[str, dict]:
    with open(path, "r") as f:
        data = yaml.safe_load(f) or {}
    lookup: Dict[str, dict] = {}
    for firm in data.get("firms", []):
        keys = list(firm.get("abbreviations", [])) + list(firm.get("normalized_variants", []))
        for k in keys:
            norm_k = normalize_employer_name(k)
            if norm_k:
                lookup[norm_k] = firm
    return lookup


def load_employer_alias_map(path: Path = EMPLOYER_ALIAS_PATH) -> Dict[str, dict]:
    with open(path, "r") as f:
        data = yaml.safe_load(f) or {}
    lookup: Dict[str, dict] = {}
    for emp in data.get("employers", []):
        for variant in emp.get("variants", []):
            norm_v = normalize_employer_name(variant)
            if norm_v:
                lookup[norm_v] = emp
    return lookup


def _build_pool(
    staffing_map: Dict[str, dict],
    alias_map: Dict[str, dict],
    extra_candidates: Optional[List[str]],
) -> Dict[str, dict]:
    pool: Dict[str, dict] = {}
    for k, firm in staffing_map.items():
        pool[k] = {
            "canonical": firm["canonical"],
            "employer_id": None,
            "is_staffing": True,
        }
    for k, emp in alias_map.items():
        pool[k] = {
            "canonical": emp.get("canonical"),
            "employer_id": emp.get("employer_id"),
            "is_staffing": bool(emp.get("is_staffing_or_consulting", False)),
        }
    for name in extra_candidates or []:
        norm = normalize_employer_name(name)
        if norm and norm not in pool:
            pool[norm] = {"canonical": name, "employer_id": None, "is_staffing": False}
    return pool


def match_employer(
    raw_input: str,
    alias_map: Optional[Dict[str, dict]] = None,
    staffing_map: Optional[Dict[str, dict]] = None,
    extra_candidates: Optional[List[str]] = None,
    threshold: float = DEFAULT_THRESHOLD,
) -> MatchResult:
    """extra_candidates lets a caller widen the fuzzy-match pool beyond the
    curated maps -- e.g. with normalized names from top_500_employers.csv
    that haven't been hand-aliased yet."""
    if alias_map is None:
        alias_map = load_employer_alias_map()
    if staffing_map is None:
        staffing_map = load_staffing_map()

    normalized_input = normalize_employer_name(raw_input)
    if not normalized_input:
        return MatchResult(input_raw=raw_input, matched=False)

    if normalized_input in staffing_map:
        firm = staffing_map[normalized_input]
        return MatchResult(
            input_raw=raw_input,
            matched=True,
            canonical=firm["canonical"],
            score=100.0,
            is_staffing_or_consulting=True,
        )

    if normalized_input in alias_map:
        emp = alias_map[normalized_input]
        return MatchResult(
            input_raw=raw_input,
            matched=True,
            canonical=emp.get("canonical"),
            employer_id=emp.get("employer_id"),
            score=100.0,
            is_staffing_or_consulting=bool(emp.get("is_staffing_or_consulting", False)),
        )

    pool = _build_pool(staffing_map, alias_map, extra_candidates)
    if not pool:
        return MatchResult(input_raw=raw_input, matched=False)

    results = process.extract(
        normalized_input, list(pool.keys()), scorer=fuzz.token_set_ratio, limit=5
    )
    candidates = [Candidate(name=pool[choice]["canonical"], score=score) for choice, score, _ in results]

    if candidates and candidates[0].score >= threshold:
        best_key = results[0][0]
        best = pool[best_key]
        return MatchResult(
            input_raw=raw_input,
            matched=True,
            canonical=best["canonical"],
            employer_id=best["employer_id"],
            score=results[0][1],
            is_staffing_or_consulting=best["is_staffing"],
            candidates=candidates,
        )

    return MatchResult(input_raw=raw_input, matched=False, candidates=candidates)
