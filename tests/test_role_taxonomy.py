import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd  # noqa: E402

from src.role_taxonomy import (  # noqa: E402
    classify_dataframe,
    classify_role,
    extract_seniority,
    load_taxonomy,
)

TAXONOMY = load_taxonomy()


def test_extract_seniority_senior():
    seniority, stripped = extract_seniority("Senior Software Engineer", TAXONOMY)
    assert seniority == "senior"
    assert stripped == "SOFTWARE ENGINEER"


def test_extract_seniority_abbreviation():
    seniority, stripped = extract_seniority("Sr. Data Engineer", TAXONOMY)
    assert seniority == "senior"
    assert stripped == "DATA ENGINEER"


def test_extract_seniority_entry_level_multiword():
    seniority, stripped = extract_seniority("Entry Level Business Analyst", TAXONOMY)
    assert seniority == "entry"
    assert stripped == "BUSINESS ANALYST"


def test_extract_seniority_none():
    seniority, stripped = extract_seniority("Software Engineer", TAXONOMY)
    assert seniority is None
    assert stripped == "SOFTWARE ENGINEER"


def test_seniority_never_strips_whole_title():
    # A title that is nothing but a seniority word must not become empty.
    _, stripped = extract_seniority("Associate", TAXONOMY)
    assert stripped == "ASSOCIATE"


def test_soc_clean_wins_outright():
    # 15-2051 is unambiguous (Data Scientists) -- title keyword can't override.
    bucket, _, source = classify_role("Software Engineer", "15-2051", TAXONOMY)
    assert bucket == "data_scientist"
    assert source == "soc_clean"


def test_keyword_refines_within_coarse_soc():
    # 15-1252 (Software Developers) is coarse; the QA title should win,
    # which is the whole point of not trusting SOC alone.
    bucket, _, source = classify_role("QA Automation Engineer", "15-1252", TAXONOMY)
    assert bucket == "qa_engineer"
    assert source == "keyword"


def test_coarse_soc_used_as_fallback_when_title_unhelpful():
    bucket, _, source = classify_role("Member of Staff", "15-1252", TAXONOMY)
    assert bucket == "software_engineer"
    assert source == "soc_coarse"


def test_longest_phrase_wins():
    bucket, _, _ = classify_role("Machine Learning Engineer", None, TAXONOMY)
    assert bucket == "ml_ai_engineer"


def test_data_engineer_synonyms_from_brief():
    for title in [
        "ETL Developer",
        "Big Data Engineer",
        "Hadoop Developer",
        "Data Warehouse Engineer",
        "Informatica Developer",
    ]:
        bucket, _, _ = classify_role(title, None, TAXONOMY)
        assert bucket == "data_engineer", f"{title} -> {bucket}"


def test_qa_synonyms_from_brief():
    for title in ["Test Engineer", "SDET", "Automation Engineer", "Quality Analyst"]:
        bucket, _, _ = classify_role(title, None, TAXONOMY)
        assert bucket == "qa_engineer", f"{title} -> {bucket}"


def test_business_analyst_synonyms_from_brief():
    for title in ["Systems Analyst", "Functional Analyst", "Business Systems Analyst"]:
        bucket, _, _ = classify_role(title, None, TAXONOMY)
        assert bucket == "business_analyst", f"{title} -> {bucket}"


def test_unmatched_falls_to_other():
    bucket, _, source = classify_role("Underwater Basket Weaver", None, TAXONOMY)
    assert bucket == "other"
    assert source == "unmatched"


def test_soc_code_format_variants_all_match():
    for soc in ["15-2051", "15-2051.00", "152051"]:
        bucket, _, source = classify_role("Whatever", soc, TAXONOMY)
        assert bucket == "data_scientist", f"{soc} -> {bucket}"
        assert source == "soc_clean"


def test_seniority_preserved_alongside_bucket():
    bucket, seniority, _ = classify_role("Principal Data Scientist", None, TAXONOMY)
    assert bucket == "data_scientist"
    assert seniority == "principal"


def test_classify_dataframe_adds_columns():
    df = pd.DataFrame(
        [
            {"job_title_raw": "Senior Software Engineer", "soc_code": "15-1252"},
            {"job_title_raw": "Underwater Basket Weaver", "soc_code": None},
        ]
    )
    out = classify_dataframe(df, TAXONOMY)
    assert list(out["role_bucket"]) == ["software_engineer", "other"]
    assert out["seniority"].iloc[0] == "senior"
    assert pd.isna(out["seniority"].iloc[1])
    assert "role_match_source" in out.columns
