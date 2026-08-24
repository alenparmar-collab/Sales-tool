import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.status import (  # noqa: E402
    is_denied_or_withdrawn,
    is_known_status,
    normalize_status,
)


def test_normalize_basic():
    assert normalize_status("certified") == "CERTIFIED"


def test_normalize_hyphen_spacing():
    assert normalize_status("Certified - Withdrawn") == "CERTIFIED-WITHDRAWN"
    assert normalize_status("CERTIFIED-WITHDRAWN") == "CERTIFIED-WITHDRAWN"


def test_normalize_none_and_blank():
    assert normalize_status(None) is None
    assert normalize_status("   ") is None


def test_flagging():
    assert is_denied_or_withdrawn("DENIED") is True
    assert is_denied_or_withdrawn("WITHDRAWN") is True
    assert is_denied_or_withdrawn("CERTIFIED") is False
    assert is_denied_or_withdrawn("CERTIFIED-WITHDRAWN") is False
    assert is_denied_or_withdrawn(None) is False


def test_known_status():
    for s in ["CERTIFIED", "CERTIFIED-WITHDRAWN", "DENIED", "WITHDRAWN"]:
        assert is_known_status(s) is True
    assert is_known_status("PENDING") is False
    assert is_known_status(None) is False


def test_certified_expired_counts_as_a_certification():
    # PERM certifications expire if the employer doesn't file the I-140
    # within 180 days. Treating this as unknown dropped 57,073 of 147,056
    # FY2025 PERM rows -- 39% -- in the first complete run. DOL approved
    # these, so they count toward "does this employer sponsor".
    s = normalize_status("Certified-Expired")
    assert s == "CERTIFIED-EXPIRED"
    assert is_known_status(s) is True
    assert is_denied_or_withdrawn(s) is False


def test_certified_expired_spacing_variant():
    assert normalize_status("Certified - Expired") == "CERTIFIED-EXPIRED"


def test_genuinely_unknown_status_still_rejected():
    # The fix must not turn the guard off entirely.
    assert is_known_status(normalize_status("In Progress")) is False
