"""Column alias resolution: map canonical field names onto whatever headers
a given DOL disclosure file actually uses, without hardcoding one fixed
schema in Python.
"""
from __future__ import annotations

import difflib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

import yaml

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "column_aliases.yaml"

# Fields every row must have to be usable. If a file kind is missing one of
# these after alias resolution, the pipeline stops rather than emitting a
# column of nulls.
REQUIRED_FIELDS = [
    "case_status",
    "decision_date",
    "employer_raw",
    "job_title_raw",
    "worksite_city",
    "worksite_state",
]

# Fields that are useful but not fatal if a given year's file lacks them.
OPTIONAL_FIELDS = [
    "case_number",
    "visa_class",
    "soc_code",
    "wage_from",
    "wage_to",
    "wage_unit",
    "wage_level",
    "full_time_flag",
]


class ColumnResolutionError(RuntimeError):
    """Raised when a required canonical field has no matching header in the
    source file. Never guess past this -- fix the alias config instead."""


def _normalize(name: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(name).upper())


def load_alias_config(path: Path = CONFIG_PATH) -> Dict[str, Dict[str, List[str]]]:
    with open(path, "r") as f:
        return yaml.safe_load(f)


@dataclass
class ResolvedColumns:
    file_kind: str
    mapping: Dict[str, Optional[str]]  # canonical field -> actual header (or None if optional+missing)

    def get(self, field: str) -> Optional[str]:
        return self.mapping.get(field)


def resolve_columns(
    actual_headers: List[str],
    file_kind: str,
    source_label: str,
    alias_config: Optional[Dict[str, Dict[str, List[str]]]] = None,
) -> ResolvedColumns:
    """Match canonical fields to the real headers of one downloaded file.

    Raises ColumnResolutionError, with the file's actual headers and the
    closest fuzzy suggestions, if a REQUIRED field can't be matched.
    """
    if alias_config is None:
        alias_config = load_alias_config()

    if file_kind not in alias_config:
        raise ColumnResolutionError(
            f"No alias config for file kind '{file_kind}'. "
            f"Known kinds: {sorted(alias_config)}"
        )

    aliases = alias_config[file_kind]
    normalized_to_actual = {_normalize(h): h for h in actual_headers}

    mapping: Dict[str, Optional[str]] = {}
    all_fields = list(dict.fromkeys(list(aliases.keys())))
    for field in all_fields:
        candidates = aliases.get(field, [])
        found = None
        for candidate in candidates:
            actual = normalized_to_actual.get(_normalize(candidate))
            if actual is not None:
                found = actual
                break
        mapping[field] = found

        if found is None and field in REQUIRED_FIELDS:
            normalized_candidates = [_normalize(c) for c in candidates]
            suggestions = []
            for nc in normalized_candidates:
                suggestions.extend(
                    difflib.get_close_matches(nc, normalized_to_actual.keys(), n=3, cutoff=0.6)
                )
            suggested_headers = sorted({normalized_to_actual[s] for s in suggestions})
            raise ColumnResolutionError(
                f"[{source_label}] Could not resolve required field '{field}' "
                f"(kind={file_kind}). Tried aliases: {candidates}.\n"
                f"Closest header matches found in file: {suggested_headers or 'none'}\n"
                f"All headers in file ({len(actual_headers)}): {sorted(actual_headers)}\n"
                f"Fix: add the correct header name to config/column_aliases.yaml "
                f"under {file_kind}.{field} and rerun."
            )

    return ResolvedColumns(file_kind=file_kind, mapping=mapping)
