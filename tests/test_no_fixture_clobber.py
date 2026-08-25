"""Guard: nothing in the test suite may write over the published index.

This exists because it happened. A test fixture was written to the default
output path, `git add -A` swept it up, and the live site served a
two-employer stub in place of 1.78M real filings until it was spotted. The
data file IS the product here, so a test that can overwrite it is a live
outage waiting to happen.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.build_index import DEFAULT_OUTPUT  # noqa: E402

REAL_INDEX_MIN_EMPLOYERS = 1000


def test_published_index_is_not_a_test_fixture():
    if not DEFAULT_OUTPUT.exists():
        return  # nothing published yet; the site falls back to demo mode

    with open(DEFAULT_OUTPUT) as f:
        idx = json.load(f)

    n = idx.get("meta", {}).get("employers_in_index", 0)
    assert n >= REAL_INDEX_MIN_EMPLOYERS, (
        f"{DEFAULT_OUTPUT} holds only {n} employers, which is a test fixture, "
        "not real filing data. Restore it before committing -- the live site "
        "serves this file directly."
    )
