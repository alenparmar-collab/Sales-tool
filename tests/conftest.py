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

from src.build_index import DEFAULT_OUTPUT, PROCESSED_DIR  # noqa: E402

# Every file a test run can leave behind that a human would then commit as
# though it were real output. The index is what the site serves; the two
# CSVs are the inputs to hand curation. All three have been committed as
# fixtures at least once.
PROTECTED = [
    DEFAULT_OUTPUT,
    PROCESSED_DIR / "top_500_employers.csv",
    PROCESSED_DIR / "unmatched_titles_top_100.csv",
]


@pytest.fixture(scope="session", autouse=True)
def protect_published_data(tmp_path_factory):
    backup_dir = tmp_path_factory.mktemp("published-data")
    before = {}
    for path in PROTECTED:
        if path.exists():
            shutil.copy2(path, backup_dir / path.name)
            before[path] = path.stat().st_size

    yield

    for path in PROTECTED:
        if path in before:
            if not path.exists() or path.stat().st_size != before[path]:
                shutil.copy2(backup_dir / path.name, path)
                print(f"\n[conftest] Restored {path} -- a test overwrote it.")
        elif path.exists():
            # Did not exist before the run, so whatever is here now is a
            # fixture. Leaving it is how it gets committed by accident.
            path.unlink()
            print(f"\n[conftest] Removed {path} -- created by a test.")
