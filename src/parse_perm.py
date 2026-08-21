"""Read a downloaded PERM disclosure .xlsx into a raw DataFrame and hand it
to the shared normalizer. file_kind distinguishes the legacy ETA-9089
layout from the revised-form layout -- the caller (pipeline.py) knows which
based on how discover_sources.py classified the file.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from .normalize import normalize_file


def read_perm_file(path: Path) -> pd.DataFrame:
    return pd.read_excel(path, engine="openpyxl", dtype=str)


def parse_perm_file(path: Path, file_kind: str):
    if file_kind not in ("PERM_LEGACY", "PERM_REVISED"):
        raise ValueError(f"Unexpected PERM file_kind: {file_kind}")
    raw_df = read_perm_file(path)
    return normalize_file(raw_df, file_kind=file_kind, program="PERM", source_label=path.name)
