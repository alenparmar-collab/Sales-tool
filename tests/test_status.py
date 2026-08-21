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
