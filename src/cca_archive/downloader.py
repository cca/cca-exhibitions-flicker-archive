"""Async image downloader with concurrency limiting."""

import asyncio
from pathlib import Path
from urllib.parse import urlparse

import httpx
from rich.console import Console
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    TextColumn,
    TimeElapsedColumn,
)

from .models import PhotoRecord

_console = Console(stderr=True)


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
    concurrency: int = 3,
) -> list[PhotoRecord]:
    """Download photos concurrently, returning updated PhotoRecords with local_filename set."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    semaphore = asyncio.Semaphore(concurrency)
    updated: list[PhotoRecord] = []

    # Shared backoff: when any task gets a 429, all tasks pause before their
    # next request.  Safe without locks because asyncio is single-threaded.
    backoff_until: float = 0.0

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
                nonlocal backoff_until

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
                    max_attempts = 5  # 1 initial + 4 retries
                    last_exc: httpx.HTTPError | None = None
                    for attempt in range(max_attempts):
                        # Honour shared backoff set by any task's 429
                        loop = asyncio.get_event_loop()
                        now = loop.time()
                        if backoff_until > now:
                            await asyncio.sleep(backoff_until - now)

                        try:
                            resp = await client.get(url)
                            resp.raise_for_status()
                            filepath.write_bytes(resp.content)
                            progress.advance(task)
                            return photo.model_copy(update={"local_filename": filename})
                        except (httpx.TimeoutException, httpx.HTTPStatusError) as exc:
                            is_429 = (
                                isinstance(exc, httpx.HTTPStatusError)
                                and exc.response.status_code == 429
                            )
                            is_retryable = isinstance(exc, httpx.TimeoutException) or (
                                isinstance(exc, httpx.HTTPStatusError)
                                and exc.response.status_code in (429, *range(500, 600))
                            )
                            if is_retryable and attempt < max_attempts - 1:
                                last_exc = exc
                                if is_429:
                                    retry_after = exc.response.headers.get("Retry-After")
                                    if retry_after:
                                        delay = float(retry_after)
                                    else:
                                        delay = 4 * 2**attempt  # 4s, 8s, 16s, 32s
                                    # Set shared backoff so ALL tasks wait
                                    backoff_until = asyncio.get_event_loop().time() + delay
                                    _console.print(
                                        f"[yellow]429 rate-limited — all downloads pausing {delay:.0f}s[/yellow]"
                                    )
                                else:
                                    delay = 2**attempt  # 1s, 2s, 4s, 8s
                                await asyncio.sleep(delay)
                                continue
                            last_exc = exc
                            break
                        except httpx.HTTPError as exc:
                            last_exc = exc
                            break

                    _console.print(
                        f"[bold red]Download failed[/bold red] photo {photo.photo_id}: {last_exc}"
                    )
                    progress.advance(task)
                    return photo

            tasks = [_download(photo) for photo in photos]
            updated = await asyncio.gather(*tasks)

    return list(updated)
