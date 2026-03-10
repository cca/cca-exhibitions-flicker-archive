"""Tests for CSV export functionality."""

import csv
from datetime import date, datetime

from cca_archive.csv_export import CSV_COLUMNS, export_album_csv
from cca_archive.models import AlbumRecord, ExhibitionMetadata, PhotoRecord


def _make_photo(**overrides) -> PhotoRecord:
    defaults = {
        "photo_id": "111",
        "title": "Gallery shot 1",
        "description": "A wide view of the gallery",
        "tags": ["art", "gallery", "opening"],
        "date_taken": datetime(2024, 3, 15, 14, 30),
        "date_uploaded": datetime(2024, 3, 20, 10, 0),
        "views": 42,
        "license": "CC BY-NC 2.0",
        "original_url": "https://flickr.com/photos/111/original.jpg",
        "local_filename": "gallery_shot_1.jpg",
    }
    defaults.update(overrides)
    return PhotoRecord(**defaults)


def _make_exhibition(**overrides) -> ExhibitionMetadata:
    defaults = {
        "exhibition_title": "Luminous Terrain",
        "artists": ["Alice Nguyen", "Ben Torres"],
        "curator": "Clara Voss",
        "venue": "CCA Wattis Institute",
        "opening_date": date(2024, 3, 1),
        "closing_date": date(2024, 5, 15),
        "reception_date": date(2024, 3, 1),
        "medium": "Mixed media installation",
        "description_summary": "A two-person show exploring landscape and light.",
        "raw_description": "Luminous Terrain\nAlice Nguyen and Ben Torres\nMarch 1 - May 15, 2024",
    }
    defaults.update(overrides)
    return ExhibitionMetadata(**defaults)


def _make_album(**overrides) -> AlbumRecord:
    defaults = {
        "album_id": "72157700001",
        "album_url": "https://www.flickr.com/photos/cca/albums/72157700001",
        "title": "Luminous Terrain -- Spring 2024",
        "description": "Photos from the opening reception.",
        "photo_count": 2,
        "date_created": datetime(2024, 3, 20, 9, 0),
    }
    defaults.update(overrides)
    return AlbumRecord(**defaults)


def _read_csv(path):
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    return rows


# ---- Main happy-path test ----


def test_export_album_csv_full(tmp_path):
    """Export an album with exhibition metadata and two photos; verify contents."""
    photo_a = _make_photo(
        photo_id="111",
        title="Gallery shot 1",
        tags=["art", "gallery"],
        views=42,
    )
    photo_b = _make_photo(
        photo_id="222",
        title="Detail of installation",
        tags=["detail"],
        date_taken=datetime(2024, 3, 16, 11, 0),
        views=7,
        original_url=None,
        large_url="https://flickr.com/photos/222/large.jpg",
        local_filename=None,
    )
    exhibition = _make_exhibition()
    album = _make_album(exhibition=exhibition, photos=[photo_a, photo_b])

    result_path = export_album_csv(album, tmp_path)

    # File exists and is in the expected directory
    assert result_path.exists()
    assert result_path.parent == tmp_path
    assert result_path.suffix == ".csv"

    rows = _read_csv(result_path)

    # Correct number of data rows (one per photo)
    assert len(rows) == 2

    # Headers match the declared columns
    with open(result_path, newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader)
    assert header == CSV_COLUMNS

    # --- Row 0: photo_a ---
    r0 = rows[0]
    assert r0["album_id"] == "72157700001"
    assert r0["album_title"] == "Luminous Terrain -- Spring 2024"
    assert r0["album_url"] == "https://www.flickr.com/photos/cca/albums/72157700001"
    assert r0["album_photo_count"] == "2"
    assert r0["album_date_created"] == "2024-03-20T09:00:00"

    # Exhibition fields
    assert r0["exhibition_title"] == "Luminous Terrain"
    assert r0["artists"] == "Alice Nguyen; Ben Torres"
    assert r0["curator"] == "Clara Voss"
    assert r0["venue"] == "CCA Wattis Institute"
    assert r0["opening_date"] == "2024-03-01"
    assert r0["closing_date"] == "2024-05-15"
    assert r0["reception_date"] == "2024-03-01"
    assert r0["medium"] == "Mixed media installation"
    assert r0["description_summary"] == "A two-person show exploring landscape and light."

    # Photo-specific fields
    assert r0["photo_id"] == "111"
    assert r0["photo_title"] == "Gallery shot 1"
    assert r0["photo_tags"] == "art; gallery"
    assert r0["date_taken"] == "2024-03-15T14:30:00"
    assert r0["photo_views"] == "42"
    assert r0["original_url"] == "https://flickr.com/photos/111/original.jpg"
    assert r0["local_filename"] == "gallery_shot_1.jpg"

    # --- Row 1: photo_b (falls back to large_url, no local filename) ---
    r1 = rows[1]
    assert r1["photo_id"] == "222"
    assert r1["original_url"] == "https://flickr.com/photos/222/large.jpg"
    assert r1["local_filename"] == ""
    assert r1["photo_tags"] == "detail"


# ---- Edge case: no exhibition metadata ----


def test_export_album_no_exhibition(tmp_path):
    """Album without exhibition metadata should leave exhibition columns empty."""
    photo = _make_photo()
    album = _make_album(
        title="Untitled Album",
        exhibition=None,
        photos=[photo],
        description="Some raw description",
    )

    result_path = export_album_csv(album, tmp_path)
    rows = _read_csv(result_path)

    assert len(rows) == 1
    r = rows[0]

    # All exhibition-specific columns should be empty strings
    assert r["exhibition_title"] == ""
    assert r["artists"] == ""
    assert r["curator"] == ""
    assert r["venue"] == ""
    assert r["opening_date"] == ""
    assert r["closing_date"] == ""
    assert r["medium"] == ""
    assert r["description_summary"] == ""

    # raw_description falls back to album.description when no exhibition
    assert r["raw_description"] == "Some raw description"

    # Photo data should still be present
    assert r["photo_id"] == "111"


# ---- Edge case: no photos -> header-only CSV ----


def test_export_album_no_photos(tmp_path):
    """Album with no photos should produce a CSV with headers only."""
    exhibition = _make_exhibition()
    album = _make_album(exhibition=exhibition, photos=[], photo_count=0)

    result_path = export_album_csv(album, tmp_path)
    assert result_path.exists()

    with open(result_path, newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader)
        data_rows = list(reader)

    assert header == CSV_COLUMNS
    assert len(data_rows) == 0
