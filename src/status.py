"""Case status normalization and classification.

DOL disclosure files contain only final determinations, but the two
programs do not use the same set of them, and assuming they did cost real
data: the first complete run dropped 57,073 of 147,056 FY2025 PERM rows
(39%) and 16,287 FY2026 PERM rows (14%) as "unknown status", while LCA
dropped none. The difference is CERTIFIED-EXPIRED -- a PERM labor
certification that DOL approved but the employer never used within the
180-day window. LCA has no equivalent.

CERTIFIED-EXPIRED counts toward the main total. The question this product
answers is whether an employer sponsors, and a certified-then-expired PERM
is an approval that happened: DOL granted it. That the employer did not go
on to file the I-140 is a different fact, and the exact value is preserved
in case_status so it can be separated downstream.

Anything still unrecognized is dropped but counted and named in the run
report (see report.unknown_status_counts) rather than disappearing
quietly -- silence is what let 39% of PERM go missing in the first place.
"""
from __future__ import annotations

import re
from typing import Optional

MAIN_STATUSES = {"CERTIFIED", "CERTIFIED-WITHDRAWN", "CERTIFIED-EXPIRED"}
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
