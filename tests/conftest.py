"""Protect the published data index from the test suite.

web/data/index.json is not a build artifact -- it is what the live site
serves. A test that writes to the default output path therefore replaces
production data, and `git add -A` will happily commit it. That has already
happened twice: the site served a two-employer fixture in place of 1.78M
filings until it was noticed.

An ordinary guard test cannot catch this, because pytest runs files
alphabetically and the offender may run after the guard. This fixture is
autouse and session-scoped, so it wraps the entire run: it snapshots the
file before any test executes and restores it afterwards if anything
changed. Tests that write the index still pass; they just cannot leave the
damage behind.

The root-cause fix is for each test to redirect the path (see
test_pipeline_integration.py). This is the net under that.
"""
import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.build_index import DEFAULT_OUTPUT  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def protect_published_index(tmp_path_factory):
    if not DEFAULT_OUTPUT.exists():
        yield
        # Nothing was published before the run; anything a test created here
        # is a fixture and must not be left where the site would serve it.
        if DEFAULT_OUTPUT.exists():
            DEFAULT_OUTPUT.unlink()
        return

    backup = tmp_path_factory.mktemp("published-index") / "index.json"
    shutil.copy2(DEFAULT_OUTPUT, backup)
    before = DEFAULT_OUTPUT.stat().st_size

    yield

    if not DEFAULT_OUTPUT.exists() or DEFAULT_OUTPUT.stat().st_size != before:
        shutil.copy2(backup, DEFAULT_OUTPUT)
        print(
            f"\n[conftest] Restored {DEFAULT_OUTPUT} -- a test overwrote the "
            f"published index ({before} bytes). Redirect the output path in "
            "that test."
        )
