"""Tests for manifest CRUD operations."""

import json
from pathlib import Path

import pytest

from cca_archive.manifest import (
    get_failed_llm_slugs,
    load_manifest,
    save_manifest,
    update_stage,
)


class FakeSettings:
    """Minimal settings stand-in that provides manifest_path."""

    def __init__(self, tmp_path: Path) -> None:
        self.manifest_path = tmp_path / "manifest.json"


# ---- load_manifest ----


def test_load_manifest_missing(tmp_path):
    """Returns empty dict when manifest file does not exist."""
    settings = FakeSettings(tmp_path)
    result = load_manifest(settings)
    assert result == {}


# ---- save_manifest / load_manifest roundtrip ----


def test_save_and_load_roundtrip(tmp_path):
    """Data written by save_manifest is returned unchanged by load_manifest."""
    settings = FakeSettings(tmp_path)
    data = {
        "some-album": {
            "album_id": "72177720001",
            "title": "Some Album",
            "slug": "some-album",
            "stages": {
                "llm_extraction": {"status": "success", "timestamp": "2026-04-13T00:00:00+00:00", "error": None},
            },
            "updated_at": "2026-04-13T00:00:00+00:00",
        }
    }
    save_manifest(data, settings)
    loaded = load_manifest(settings)
    assert loaded == data


def test_save_manifest_is_atomic(tmp_path):
    """save_manifest uses a .tmp file then renames; no .tmp remains after save."""
    settings = FakeSettings(tmp_path)
    save_manifest({"a": {}}, settings)
    tmp_file = settings.manifest_path.with_suffix(".tmp")
    assert not tmp_file.exists()
    assert settings.manifest_path.exists()


# ---- update_stage ----


def test_update_stage_creates_entry(tmp_path):
    """update_stage creates a new album entry when the slug is absent."""
    manifest: dict = {}
    update_stage(
        manifest, "test-album", "72177720001", "Test Album",
        "llm_extraction", "success", error=None,
    )

    assert "test-album" in manifest
    entry = manifest["test-album"]
    assert entry["album_id"] == "72177720001"
    assert entry["title"] == "Test Album"
    assert entry["slug"] == "test-album"
    assert entry["updated_at"] != ""

    stage = entry["stages"]["llm_extraction"]
    assert stage["status"] == "success"
    assert "timestamp" in stage
    assert stage["error"] is None


def test_update_stage_updates_existing_without_clobbering(tmp_path):
    """Updating one stage does not remove other stages on the same album."""
    manifest: dict = {}
    update_stage(
        manifest, "test-album", "72177720001", "Test Album",
        "llm_extraction", "success", error=None,
    )
    update_stage(
        manifest, "test-album", "72177720001", "Test Album",
        "image_download", "success", downloaded=5, total=5,
    )

    # Now update llm_extraction to failed
    update_stage(
        manifest, "test-album", "72177720001", "Test Album",
        "llm_extraction", "failed", error="HTTP 529 Overloaded",
    )

    stages = manifest["test-album"]["stages"]
    assert stages["llm_extraction"]["status"] == "failed"
    assert stages["llm_extraction"]["error"] == "HTTP 529 Overloaded"

    # image_download must not be clobbered
    assert stages["image_download"]["status"] == "success"
    assert stages["image_download"]["downloaded"] == 5
    assert stages["image_download"]["total"] == 5


def test_update_stage_extra_kwargs_stored(tmp_path):
    """Extra kwargs (downloaded, total, path) are stored in the stage entry."""
    manifest: dict = {}
    update_stage(
        manifest, "my-album", "999", "My Album",
        "image_download", "success", downloaded=12, total=15,
    )
    stage = manifest["my-album"]["stages"]["image_download"]
    assert stage["downloaded"] == 12
    assert stage["total"] == 15


# ---- get_failed_llm_slugs ----


def test_get_failed_llm_slugs_returns_correct_set():
    """Only slugs with llm_extraction.status == 'failed' are returned."""
    manifest = {
        "album-a": {"stages": {"llm_extraction": {"status": "success"}}},
        "album-b": {"stages": {"llm_extraction": {"status": "failed"}}},
        "album-c": {"stages": {"llm_extraction": {"status": "skipped"}}},
        "album-d": {"stages": {"llm_extraction": {"status": "failed"}}},
        "album-e": {"stages": {}},  # no llm_extraction key at all
    }
    result = get_failed_llm_slugs(manifest)
    assert result == {"album-b", "album-d"}


def test_get_failed_llm_slugs_empty_manifest():
    assert get_failed_llm_slugs({}) == set()


def test_get_failed_llm_slugs_no_failures():
    manifest = {
        "album-a": {"stages": {"llm_extraction": {"status": "success"}}},
        "album-b": {"stages": {"llm_extraction": {"status": "skipped"}}},
    }
    assert get_failed_llm_slugs(manifest) == set()
