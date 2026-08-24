"""Role bucket classification: turn free-text job titles + SOC codes into a
fixed set of buckets, and pull seniority out into its own column.

SOC alone is too coarse (15-1252 "Software Developers" covers a QA tester
and a principal engineer alike) and titles alone are noisy free text, so
this uses both: SOC codes that map unambiguously win outright, titles
decide next, and coarse SOC codes act only as a fallback default -- which
lets a title keyword refine within a broad SOC rather than be overruled
by it.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd
import yaml

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "role_taxonomy.yaml"

BUCKETS = [
    "software_engineer",
    "data_engineer",
    "data_analyst",
    "data_scientist",
    "ml_ai_engineer",
    "qa_engineer",
    "business_analyst",
    "devops_sre",
    "product_manager",
    "security_engineer",
    "finance_analyst",
    "healthcare_admin",
    "mechanical_engineer",
    "electrical_engineer",
    "civil_engineer",
    "other",
]

_PUNCT_RE = re.compile(r"[^A-Z0-9]")
_WHITESPACE_RE = re.compile(r"\s+")


@dataclass
class RoleTaxonomy:
    seniority_tokens: Dict[str, List[str]]
    soc_clean: Dict[str, str]
    soc_coarse: Dict[str, str]
    keywords: Dict[str, List[str]]
    # keyword phrases pre-sorted longest-first so "DATA ENGINEER" is tested
    # before a bare "ENGINEER" and wins.
    _ordered_phrases: List[Tuple[str, str]]


def load_taxonomy(path: Path = CONFIG_PATH) -> RoleTaxonomy:
    with open(path, "r") as f:
        cfg = yaml.safe_load(f) or {}

    keywords = cfg.get("keywords", {}) or {}
    phrases: List[Tuple[str, str]] = []
    for bucket, phrase_list in keywords.items():
        for phrase in phrase_list or []:
            phrases.append((_normalize_title(phrase), bucket))
    phrases.sort(key=lambda p: len(p[0].split()), reverse=True)

    return RoleTaxonomy(
        seniority_tokens=cfg.get("seniority_tokens", {}) or {},
        soc_clean={_normalize_soc(k): v for k, v in (cfg.get("soc_clean") or {}).items()},
        soc_coarse={_normalize_soc(k): v for k, v in (cfg.get("soc_coarse") or {}).items()},
        keywords=keywords,
        _ordered_phrases=phrases,
    )


def _normalize_soc(raw: object) -> str:
    """DOL writes SOC codes inconsistently (15-1252, 15-1252.00, 151252).
    Reduce to bare digits so all three forms compare equal; keep only the
    first 6 digits, dropping any .00 detail suffix."""
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return ""
    digits = re.sub(r"[^0-9]", "", str(raw))
    return digits[:6]


def _normalize_title(raw: object) -> str:
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return ""
    s = _PUNCT_RE.sub(" ", str(raw).upper())
    return _WHITESPACE_RE.sub(" ", s).strip()


def extract_seniority(title: object, taxonomy: Optional[RoleTaxonomy] = None) -> Tuple[Optional[str], str]:
    """Pull a seniority level out of the title and return
    (seniority, title_without_seniority). Seniority is kept, not discarded --
    it feeds the 'do they file at this level' signal later.
    """
    if taxonomy is None:
        taxonomy = load_taxonomy()

    normalized = _normalize_title(title)
    if not normalized:
        return None, ""

    tokens = normalized.split(" ")
    found: Optional[str] = None

    # Longest token-phrases first ("ENTRY LEVEL" before "ENTRY").
    candidates: List[Tuple[List[str], str]] = []
    for level, variants in taxonomy.seniority_tokens.items():
        for variant in variants:
            candidates.append((_normalize_title(variant).split(" "), level))
    candidates.sort(key=lambda c: len(c[0]), reverse=True)

    changed = True
    while changed:
        changed = False
        for phrase_tokens, level in candidates:
            n = len(phrase_tokens)
            if len(tokens) > n:
                for i in range(len(tokens) - n + 1):
                    if tokens[i : i + n] == phrase_tokens:
                        if found is None:
                            found = level
                        tokens = tokens[:i] + tokens[i + n :]
                        changed = True
                        break
            if changed:
                break

    return found, " ".join(tokens)


def classify_role(
    job_title: object,
    soc_code: object = None,
    taxonomy: Optional[RoleTaxonomy] = None,
) -> Tuple[str, Optional[str], str]:
    """Returns (role_bucket, seniority, match_source).

    match_source is one of soc_clean / keyword / soc_coarse / unmatched --
    kept so the first-pass review can see WHY something landed where it did.
    """
    if taxonomy is None:
        taxonomy = load_taxonomy()

    seniority, stripped_title = extract_seniority(job_title, taxonomy)
    soc = _normalize_soc(soc_code)

    if soc and soc in taxonomy.soc_clean:
        return taxonomy.soc_clean[soc], seniority, "soc_clean"

    if stripped_title:
        padded = f" {stripped_title} "
        for phrase, bucket in taxonomy._ordered_phrases:
            if phrase and f" {phrase} " in padded:
                return bucket, seniority, "keyword"

    if soc and soc in taxonomy.soc_coarse:
        return taxonomy.soc_coarse[soc], seniority, "soc_coarse"

    return "other", seniority, "unmatched"


def classify_dataframe(df: pd.DataFrame, taxonomy: Optional[RoleTaxonomy] = None) -> pd.DataFrame:
    """Add role_bucket, seniority, and role_match_source columns."""
    if taxonomy is None:
        taxonomy = load_taxonomy()

    results = [
        classify_role(title, soc, taxonomy)
        for title, soc in zip(df["job_title_raw"], df.get("soc_code", pd.Series([None] * len(df))))
    ]
    out = df.copy()
    out["role_bucket"] = [r[0] for r in results]
    out["seniority"] = [r[1] for r in results]
    out["role_match_source"] = [r[2] for r in results]
    return out
