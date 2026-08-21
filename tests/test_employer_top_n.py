import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd  # noqa: E402

from src.employer_top_n import rank_employers  # noqa: E402


def test_rank_employers_groups_variants_and_excludes_flagged():
    df = pd.DataFrame(
        [
            {"employer_raw": "Amazon.com Services LLC", "is_denied_or_withdrawn": False},
            {"employer_raw": "Amazon Web Services Inc", "is_denied_or_withdrawn": False},
            {"employer_raw": "Amazon.com Services LLC", "is_denied_or_withdrawn": False},
            {"employer_raw": "Beta LLC", "is_denied_or_withdrawn": False},
            {"employer_raw": "Beta LLC", "is_denied_or_withdrawn": True},  # denied, excluded
        ]
    )
    ranked = rank_employers(df, top_n=10)

    amazon_com = ranked.loc[ranked["employer_normalized"] == "AMAZON COM", "filing_count"]
    amazon_web = ranked.loc[ranked["employer_normalized"] == "AMAZON WEB", "filing_count"]
    beta = ranked.loc[ranked["employer_normalized"] == "BETA", "filing_count"]

    # "AMAZON COM" and "AMAZON WEB" are different normalized keys (not
    # merged) -- that's what the alias map is for.
    assert amazon_com.iloc[0] == 2
    assert amazon_web.iloc[0] == 1
    assert beta.iloc[0] == 1  # only the non-denied Beta row counted


def test_rank_employers_respects_top_n():
    df = pd.DataFrame(
        [{"employer_raw": f"Company {i} Inc", "is_denied_or_withdrawn": False} for i in range(20)]
    )
    ranked = rank_employers(df, top_n=5)
    assert len(ranked) == 5
