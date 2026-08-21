"""Employer name normalization: collapse the many legal-entity variants of
one employer (AMAZON.COM SERVICES LLC / AMAZON WEB SERVICES INC / ...) down
to a comparable key, without merging genuinely different companies.

Order matters: replace punctuation with spaces (not delete it -- deleting
would fuse "AMAZON.COM" into "AMAZONCOM" and drift the string further from
anything else), collapse whitespace, then strip legal-suffix tokens
repeatedly off the end since real names stack more than one
("AMAZON WEB SERVICES INC" -> strip INC -> strip SERVICES -> "AMAZON WEB").
"""
from __future__ import annotations

import re
from typing import List

# Suffix phrases to strip off the end, tried longest-first so multi-word
# phrases ("AND SUBSIDIARIES", "U S A") don't get partially stripped by a
# single-word rule first.
_SUFFIX_PHRASES: List[List[str]] = [
    ["AND", "SUBSIDIARIES"],
    ["AND", "SUBSIDIARY"],
    ["U", "S", "A"],
    ["N", "A"],
    ["INC"],
    ["LLC"],
    ["LTD"],
    ["CORP"],
    ["CORPORATION"],
    ["CO"],
    ["COMPANY"],
    ["LP"],
    ["LLP"],
    ["PLLC"],
    ["PC"],
    ["USA"],
    ["US"],
    ["NA"],
    ["HOLDINGS"],
    ["GROUP"],
    ["TECHNOLOGIES"],
    ["TECHNOLOGY"],
    ["SOLUTIONS"],
    ["SERVICES"],
    ["SYSTEMS"],
    ["INTERNATIONAL"],
    ["GLOBAL"],
]
_SUFFIX_PHRASES.sort(key=len, reverse=True)

_PUNCT_RE = re.compile(r"[^A-Z0-9\s]")
_WHITESPACE_RE = re.compile(r"\s+")


def _strip_trailing_suffixes(tokens: List[str]) -> List[str]:
    changed = True
    while changed and tokens:
        changed = False
        for phrase in _SUFFIX_PHRASES:
            n = len(phrase)
            if len(tokens) > n and tokens[-n:] == phrase:
                # Keep stripping only while something would still remain --
                # never strip a name down to nothing (e.g. bare "LLC").
                tokens = tokens[:-n]
                changed = True
                break
    return tokens


def normalize_employer_name(raw: object) -> str:
    """Uppercase, strip punctuation, collapse whitespace, strip legal
    suffixes. Returns '' for missing/blank input."""
    if raw is None:
        return ""
    s = str(raw).upper()
    s = _PUNCT_RE.sub(" ", s)
    s = _WHITESPACE_RE.sub(" ", s).strip()
    if not s:
        return ""

    tokens = s.split(" ")
    tokens = _strip_trailing_suffixes(tokens)
    return " ".join(tokens)
