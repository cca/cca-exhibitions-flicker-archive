"""Upload album images to the Internet Archive."""

import asyncio
from pathlib import Path

from internetarchive import upload
from rich.console import Console
from slugify import slugify

from .config import Settings
from .models import AlbumRecord

console = Console()


def _build_ia_identifier(album: AlbumRecord) -> str:
    """Build an IA item identifier from album title."""
    return f"cca-exhibitions-{slugify(album.title)}"


def _build_ia_metadata(album: AlbumRecord) -> dict:
    """Build IA metadata dict from album + exhibition data."""
    meta: dict[str, str | list[str]] = {
        "collection": "opensource_image",
        "mediatype": "image",
        "title": album.title,
        "creator": "CCA Exhibitions",
    }

    if album.description:
        meta["description"] = album.description

    ex = album.exhibition
    if ex:
        if ex.exhibition_title:
            meta["title"] = ex.exhibition_title
        if ex.artists:
            meta["subject"] = ex.artists
        if ex.curator:
            meta["contributor"] = ex.curator
        if ex.venue:
            meta["coverage"] = ex.venue
        if ex.opening_date:
            meta["date"] = str(ex.opening_date)
        if ex.description_summary:
            meta["description"] = ex.description_summary

    return meta


async def upload_album_to_ia(
    album: AlbumRecord, image_dir: Path, settings: Settings
) -> str:
    """Upload all album images to Internet Archive. Returns IA item identifier."""
    identifier = _build_ia_identifier(album)
    album_slug = slugify(album.title)
    album_image_dir = image_dir / album_slug

    if not album_image_dir.exists():
        console.print(f"  [yellow]No images directory at {album_image_dir}, skipping IA upload[/yellow]")
        return identifier

    files = [
        f for f in album_image_dir.iterdir()
        if f.is_file() and f.suffix.lower() in {".jpg", ".jpeg", ".png", ".gif", ".tif", ".tiff"}
    ]

    if not files:
        console.print(f"  [yellow]No image files found in {album_image_dir}, skipping IA upload[/yellow]")
        return identifier

    metadata = _build_ia_metadata(album)

    console.print(f"  [bold]Uploading {len(files)} images to IA as [cyan]{identifier}[/cyan]...[/bold]")

    # internetarchive.upload is synchronous; run in executor to avoid blocking
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(
        None,
        lambda: upload(
            identifier,
            files=[str(f) for f in files],
            metadata=metadata,
            access_key=settings.ia_access_key,
            secret_key=settings.ia_secret_key,
            retries=3,
            verbose=True,
        ),
    )

    console.print(f"  [bold green]Uploaded to IA:[/bold green] https://archive.org/details/{identifier}")
    return identifier
