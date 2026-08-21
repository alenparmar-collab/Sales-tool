"""Download source files to data/raw/, with a manifest recording what was
pulled and when so reruns are auditable.
"""
from __future__ import annotations

import json
import logging
from dataclasses import asdict
from pathlib import Path
from typing import List

import requests

from .discover_sources import SourceFile, REQUEST_TIMEOUT, USER_AGENT

logger = logging.getLogger(__name__)


class DownloadError(RuntimeError):
    pass


RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"
LAYOUTS_DIR = RAW_DIR / "layouts"
MANIFEST_PATH = RAW_DIR / "download_manifest.json"


def _dest_dir(kind: str) -> Path:
    return LAYOUTS_DIR if kind == "LAYOUT" else RAW_DIR


def _dest_filename(source: SourceFile) -> str:
    return source.url.split("/")[-1].split("?")[0]


def download_sources(
    sources: List[SourceFile],
    force: bool = False,
) -> List[dict]:
    """Download each SourceFile if not already present (or always, if
    force=True -- DOL updates the current-quarter file in place under the
    same or a new name each release, so force is the safe default for the
    quarters that are still "open"; closed prior-FY files rarely change).
    """
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    LAYOUTS_DIR.mkdir(parents=True, exist_ok=True)

    manifest = []
    for source in sources:
        dest_dir = _dest_dir(source.kind)
        dest_path = dest_dir / _dest_filename(source)

        if dest_path.exists() and not force:
            logger.info("Skipping existing file: %s", dest_path)
        else:
            logger.info("Downloading %s -> %s", source.url, dest_path)
            try:
                resp = requests.get(
                    source.url, timeout=REQUEST_TIMEOUT, headers={"User-Agent": USER_AGENT}, stream=True
                )
                resp.raise_for_status()
                with open(dest_path, "wb") as f:
                    for chunk in resp.iter_content(chunk_size=1 << 20):
                        f.write(chunk)
            except requests.exceptions.RequestException as e:
                raise DownloadError(f"Failed to download {source.url}: {e}") from e

        manifest.append(
            {
                **asdict(source),
                "local_path": str(dest_path),
                "size_bytes": dest_path.stat().st_size if dest_path.exists() else None,
            }
        )

    with open(MANIFEST_PATH, "w") as f:
        json.dump(manifest, f, indent=2)

    return manifest
