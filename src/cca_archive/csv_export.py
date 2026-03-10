"""CSV export — one row per photo, album/exhibition columns repeated."""

import csv
from pathlib import Path

from .models import AlbumRecord


CSV_COLUMNS = [
    "album_id",
    "album_title",
    "album_url",
    "album_photo_count",
    "album_date_created",
    "exhibition_title",
    "artists",
    "curator",
    "venue",
    "opening_date",
    "closing_date",
    "reception_date",
    "medium",
    "description_summary",
    "raw_description",
    "photo_id",
    "photo_title",
    "photo_description",
    "photo_tags",
    "date_taken",
    "date_uploaded",
    "photo_views",
    "license",
    "original_url",
    "local_filename",
]


def export_album_csv(album: AlbumRecord, dest_dir: Path) -> Path:
    """Export an AlbumRecord to CSV. Returns the output file path."""
    dest_dir.mkdir(parents=True, exist_ok=True)

    from slugify import slugify

    filename = f"{slugify(album.title)}.csv"
    filepath = dest_dir / filename

    ex = album.exhibition

    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        writer.writeheader()

        for photo in album.photos:
            row = {
                "album_id": album.album_id,
                "album_title": album.title,
                "album_url": album.album_url,
                "album_photo_count": album.photo_count,
                "album_date_created": album.date_created.isoformat() if album.date_created else "",
                "exhibition_title": ex.exhibition_title if ex else "",
                "artists": "; ".join(ex.artists) if ex else "",
                "curator": ex.curator or "" if ex else "",
                "venue": ex.venue or "" if ex else "",
                "opening_date": str(ex.opening_date) if ex and ex.opening_date else "",
                "closing_date": str(ex.closing_date) if ex and ex.closing_date else "",
                "reception_date": str(ex.reception_date) if ex and ex.reception_date else "",
                "medium": ex.medium or "" if ex else "",
                "description_summary": ex.description_summary or "" if ex else "",
                "raw_description": ex.raw_description if ex else (album.description or ""),
                "photo_id": photo.photo_id,
                "photo_title": photo.title or "",
                "photo_description": photo.description or "",
                "photo_tags": "; ".join(photo.tags),
                "date_taken": photo.date_taken.isoformat() if photo.date_taken else "",
                "date_uploaded": photo.date_uploaded.isoformat() if photo.date_uploaded else "",
                "photo_views": photo.views,
                "license": photo.license or "",
                "original_url": photo.original_url or photo.large_url or photo.medium_url or "",
                "local_filename": photo.local_filename or "",
            }
            writer.writerow(row)

    return filepath
