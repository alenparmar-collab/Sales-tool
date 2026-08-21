import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.employer_normalize import normalize_employer_name  # noqa: E402


def test_basic_suffix_strip():
    assert normalize_employer_name("Amazon Web Services Inc") == "AMAZON WEB"


def test_multiple_stacked_suffixes():
    assert normalize_employer_name("Capital One Services LLC") == "CAPITAL ONE"


def test_dotcom_punctuation_becomes_space_not_deleted():
    # "AMAZON.COM" must not fuse into "AMAZONCOM"
    assert normalize_employer_name("Amazon.com Services LLC") == "AMAZON COM"


def test_and_subsidiaries_phrase():
    assert normalize_employer_name("Acme Corp and Subsidiaries") == "ACME"


def test_multiword_suffix_usa():
    assert normalize_employer_name("Capital One Bank U.S.A. N.A.") == "CAPITAL ONE BANK"


def test_never_strips_to_empty():
    # "LLC" alone should not be stripped down to nothing.
    assert normalize_employer_name("LLC") == "LLC"


def test_whitespace_collapse():
    assert normalize_employer_name("  Acme   Corp  ") == "ACME"


def test_blank_and_none():
    assert normalize_employer_name("") == ""
    assert normalize_employer_name(None) == ""


def test_ampersand_and_punctuation():
    assert normalize_employer_name("JPMorgan Chase & Co") == "JPMORGAN CHASE"
