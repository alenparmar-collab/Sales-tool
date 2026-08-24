"""Shared row-normalization logic: turn a raw DOL DataFrame (LCA,
PERM_LEGACY, or PERM_REVISED -- any file kind with an alias mapping) into
the common output schema.
"""
from __future__ import annotations

from typing import Tuple

import pandas as pd

from .columns import resolve_columns
from .fiscal_year import fiscal_year_series
from .status import is_denied_or_withdrawn, is_known_status, normalize_status
from .wage import annualize_wage_series

TARGET_COLUMNS = [
    # Carried through so overlapping releases can be de-duplicated and any
    # individual row traced back to DOL's own record.
    "case_number",
    "employer_raw",
    "program",
    "fiscal_year",
    "decision_date",
    "case_status",
    "job_title_raw",
    "soc_code",
    "worksite_city",
    "worksite_state",
    "wage_offered",
    "wage_unit",
    "wage_level",
    "full_time_flag",
    "is_denied_or_withdrawn",
    "source_file",
]


def _get_or_blank(df: pd.DataFrame, resolved, field: str) -> pd.Series:
    col = resolved.get(field)
    if col is None:
        return pd.Series([None] * len(df), index=df.index, dtype="object")
    return df[col]


def _clean_str(series: pd.Series) -> pd.Series:
    return series.astype("string").str.strip()


def _normalize_full_time(series: pd.Series) -> pd.Series:
    def conv(v):
        if v is None or (isinstance(v, float) and pd.isna(v)):
            return None
        s = str(v).strip().upper()
        if s in ("Y", "YES", "TRUE", "1"):
            return True
        if s in ("N", "NO", "FALSE", "0"):
            return False
        return None

    return series.map(conv)


def normalize_file(
    raw_df: pd.DataFrame, file_kind: str, program: str, source_label: str
) -> Tuple[pd.DataFrame, int, dict]:
    """Returns (normalized_df, rows_dropped, {unknown_status: count})."""
    headers = list(raw_df.columns)
    resolved = resolve_columns(headers, file_kind, source_label)

    normalized_status = _get_or_blank(raw_df, resolved, "case_status").map(normalize_status)

    out = pd.DataFrame(index=raw_df.index)
    out["case_number"] = _clean_str(_get_or_blank(raw_df, resolved, "case_number"))
    out["employer_raw"] = _clean_str(_get_or_blank(raw_df, resolved, "employer_raw"))
    out["program"] = program
    out["decision_date"] = pd.to_datetime(
        _get_or_blank(raw_df, resolved, "decision_date"), errors="coerce"
    )
    out["fiscal_year"] = fiscal_year_series(out["decision_date"])
    out["case_status"] = normalized_status
    out["job_title_raw"] = _clean_str(_get_or_blank(raw_df, resolved, "job_title_raw"))
    out["soc_code"] = _clean_str(_get_or_blank(raw_df, resolved, "soc_code"))
    out["worksite_city"] = _clean_str(_get_or_blank(raw_df, resolved, "worksite_city"))
    out["worksite_state"] = _clean_str(_get_or_blank(raw_df, resolved, "worksite_state"))

    wage_from = pd.to_numeric(_get_or_blank(raw_df, resolved, "wage_from"), errors="coerce")
    wage_to = pd.to_numeric(_get_or_blank(raw_df, resolved, "wage_to"), errors="coerce")
    wage_amount = wage_from.where(wage_from.notna(), wage_to)
    wage_unit_raw = _get_or_blank(raw_df, resolved, "wage_unit")
    out["wage_offered"] = annualize_wage_series(wage_amount, wage_unit_raw)
    out["wage_unit"] = _clean_str(wage_unit_raw)
    out["wage_level"] = _clean_str(_get_or_blank(raw_df, resolved, "wage_level"))
    out["full_time_flag"] = _normalize_full_time(_get_or_blank(raw_df, resolved, "full_time_flag"))
    out["is_denied_or_withdrawn"] = normalized_status.map(is_denied_or_withdrawn)
    out["source_file"] = source_label

    # Disclosure files should only contain final determinations (CERTIFIED,
    # Anything not in status.KNOWN_STATUSES is dropped rather than kept with
    # an unclassified status -- but the distinct values and their counts are
    # returned so the run report can name them. Reporting only the total
    # dropped is what let 39% of PERM go missing behind a single number.
    known_mask = normalized_status.map(is_known_status).fillna(False)
    unknown_counts = {
        str(k): int(v)
        for k, v in normalized_status.loc[~known_mask].value_counts().items()
    }
    rows_dropped = int((~known_mask).sum())
    out = out.loc[known_mask].reset_index(drop=True)

    return out[TARGET_COLUMNS], rows_dropped, unknown_counts
