"""Read a downloaded LCA disclosure .xlsx into a raw DataFrame and hand it
to the shared normalizer. LCA files are always a single sheet."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from .normalize import normalize_file


def read_lca_file(path: Path) -> pd.DataFrame:
    return pd.read_excel(path, engine="openpyxl", dtype=str)


def parse_lca_file(path: Path):
    raw_df = read_lca_file(path)
    return normalize_file(raw_df, file_kind="LCA", program="LCA", source_label=path.name)
