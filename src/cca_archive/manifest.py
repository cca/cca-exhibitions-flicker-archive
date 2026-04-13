"""Manifest CRUD — tracks per-stage pipeline status for each album."""

import json
from datetime import datetime, timezone
from typing import Any

from .config import Settings


def load_manifest(settings: Settings) -> dict:
    """Read manifest.json; return {} if missing."""
    path = settings.manifest_path
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_manifest(manifest: dict, settings: Settings) -> None:
    """Atomic write: write to .tmp then rename."""
    path = settings.manifest_path
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
    tmp.rename(path)


def update_stage(
    manifest: dict,
    slug: str,
    album_id: str,
    title: str,
    stage: str,
    status: str,
    **kwargs: Any,
) -> None:
    """Upsert a stage entry with ISO timestamp; create album entry if absent."""
    if slug not in manifest:
        manifest[slug] = {
            "album_id": album_id,
            "title": title,
            "slug": slug,
            "stages": {},
            "updated_at": "",
        }
    entry: dict[str, Any] = {
        "status": status,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    entry.update(kwargs)
    manifest[slug]["stages"][stage] = entry
    manifest[slug]["updated_at"] = datetime.now(timezone.utc).isoformat()


def get_failed_llm_slugs(manifest: dict) -> set[str]:
    """Return slugs where llm_extraction.status == 'failed'."""
    return {
        slug
        for slug, entry in manifest.items()
        if entry.get("stages", {}).get("llm_extraction", {}).get("status") == "failed"
    }
