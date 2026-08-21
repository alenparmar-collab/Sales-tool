"""Case status normalization and classification.

DOL disclosure files only ever contain final determinations, so
case_status should only ever be one of: CERTIFIED, CERTIFIED-WITHDRAWN,
DENIED, WITHDRAWN. All four are kept in the output; DENIED/WITHDRAWN are
marked with is_denied_or_withdrawn=True so they can be excluded from main
counts while still being available for denial-rate analysis later.
"""
from __future__ import annotations

import re
from typing import Optional

MAIN_STATUSES = {"CERTIFIED", "CERTIFIED-WITHDRAWN"}
FLAGGED_STATUSES = {"DENIED", "WITHDRAWN"}
KNOWN_STATUSES = MAIN_STATUSES | FLAGGED_STATUSES


def normalize_status(raw: object) -> Optional[str]:
    """Uppercase, collapse whitespace/hyphen spacing: 'Certified - Withdrawn'
    -> 'CERTIFIED-WITHDRAWN'."""
    if raw is None:
        return None
    s = str(raw).strip().upper()
    if not s:
        return None
    s = re.sub(r"\s*-\s*", "-", s)
    s = re.sub(r"\s+", " ", s)
    return s


def is_denied_or_withdrawn(normalized_status: Optional[str]) -> bool:
    return normalized_status in FLAGGED_STATUSES


def is_known_status(normalized_status: Optional[str]) -> bool:
    return normalized_status in KNOWN_STATUSES
