import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.employer_match import match_employer  # noqa: E402

# A synthetic reference universe standing in for a real top-500 alias map
# (this pipeline has never had real DOL data to build one from -- see
# README.md). Variants are realistic filer-name patterns for these
# companies, illustrative rather than pulled from a live file.
ALIAS_MAP_FIXTURE = {
    "canonical_by_key": {
        "AMAZON COM": "Amazon",
        "AMAZON WEB": "Amazon",
        "AMAZON DEVELOPMENT CENTER U S": "Amazon",
        "GOOGLE": "Google",
        "META PLATFORMS": "Meta",
        "FACEBOOK": "Meta",
        "JPMORGAN CHASE": "JPMorgan Chase",
        "J P MORGAN SECURITIES": "JPMorgan Chase",
        "CAPITAL ONE": "Capital One",
        "CAPITAL ONE BANK": "Capital One",
        "CAPITAL ONE FINANCIAL": "Capital One",
        "WALMART": "Walmart",
        "WAL MART ASSOCIATES": "Walmart",
        "WALMART STORES": "Walmart",
    }
}


def _fixture_alias_map():
    return {
        key: {"canonical": name, "employer_id": name.lower().replace(" ", "_")}
        for key, name in ALIAS_MAP_FIXTURE["canonical_by_key"].items()
    }


def test_exact_alias_match():
    r = match_employer("Amazon.com Services LLC", alias_map=_fixture_alias_map(), staffing_map={})
    assert r.matched is True
    assert r.canonical == "Amazon"
    assert r.score == 100.0


def test_fuzzy_match_close_variant():
    # Not in the alias map verbatim, but close enough to "AMAZON WEB".
    r = match_employer(
        "Amazon Web Services LLC", alias_map=_fixture_alias_map(), staffing_map={}
    )
    assert r.matched is True
    assert r.canonical == "Amazon"


def test_below_threshold_returns_no_match_with_candidates():
    r = match_employer(
        "Completely Unrelated Widget Factory", alias_map=_fixture_alias_map(), staffing_map={}
    )
    assert r.matched is False
    assert len(r.candidates) > 0


def test_staffing_map_abbreviation_short_circuits():
    from src.employer_match import load_staffing_map

    r = match_employer("TCS", alias_map={}, staffing_map=load_staffing_map())
    assert r.matched is True
    assert r.canonical == "Tata Consultancy Services"
    assert r.is_staffing_or_consulting is True


def test_staffing_map_full_name_variant():
    from src.employer_match import load_staffing_map

    r = match_employer(
        "Cognizant Technology Solutions US Corp", alias_map={}, staffing_map=load_staffing_map()
    )
    assert r.matched is True
    assert r.canonical == "Cognizant"
    assert r.is_staffing_or_consulting is True


def test_empty_input_no_match():
    r = match_employer("", alias_map=_fixture_alias_map(), staffing_map={})
    assert r.matched is False
    assert r.candidates == []


def test_real_staffing_config_loads():
    # Sanity check that the shipped config file parses and matches TCS,
    # Infosys, Cognizant, Deloitte -- the four staffing/consulting firms
    # named in the build brief's test list.
    from src.employer_match import load_staffing_map

    staffing_map = load_staffing_map()
    for company in ["TCS", "Infosys", "Cognizant", "Deloitte"]:
        r = match_employer(company, alias_map={}, staffing_map=staffing_map)
        assert r.matched is True, f"{company} should resolve via the staffing map"
        assert r.is_staffing_or_consulting is True
