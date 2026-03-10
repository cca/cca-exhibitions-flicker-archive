"""Async image downloader with concurrency limiting."""

import asyncio
from pathlib import Path
from urllib.parse import urlparse

import httpx
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    TextColumn,
    TimeElapsedColumn,
)

from .models import PhotoRecord


def _get_download_url(photo: PhotoRecord) -> str | None:
    """Pick best available URL: original → large → medium."""
    return photo.original_url or photo.large_url or photo.medium_url


def _get_extension(url: str) -> str:
    """Extract file extension from URL path."""
    path = urlparse(url).path
    ext = Path(path).suffix
    return ext if ext else ".jpg"


async def download_photos(
    photos: list[PhotoRecord],
    dest_dir: Path,
    concurrency: int = 5,
) -> list[PhotoRecord]:
    """Download photos concurrently, returning updated PhotoRecords with local_filename set."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    semaphore = asyncio.Semaphore(concurrency)
    updated: list[PhotoRecord] = []

    progress = Progress(
        TextColumn("[bold blue]Downloading"),
        BarColumn(),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
    )

    async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
        with progress:
            task = progress.add_task("Photos", total=len(photos))

            async def _download(photo: PhotoRecord) -> PhotoRecord:
                url = _get_download_url(photo)
                if url is None:
                    progress.advance(task)
                    return photo

                ext = _get_extension(url)
                filename = f"{photo.photo_id}{ext}"
                filepath = dest_dir / filename

                # Skip if already downloaded
                if filepath.exists() and filepath.stat().st_size > 0:
                    progress.advance(task)
                    return photo.model_copy(update={"local_filename": filename})

                async with semaphore:
                    try:
                        resp = await client.get(url)
                        resp.raise_for_status()
                        filepath.write_bytes(resp.content)
                        progress.advance(task)
                        return photo.model_copy(update={"local_filename": filename})
                    except httpx.HTTPError:
                        progress.advance(task)
                        return photo

            tasks = [_download(photo) for photo in photos]
            updated = await asyncio.gather(*tasks)

    return list(updated)
