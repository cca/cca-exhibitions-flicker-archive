"""Optimize downloaded JPEGs for web serving: resize and compress to JPEG."""

import asyncio
from pathlib import Path

from rich.console import Console
from rich.progress import BarColumn, MofNCompleteColumn, Progress, TextColumn, TimeElapsedColumn

_console = Console()

FULL_MAX_SIDE = 2560
THUMB_MAX_SIDE = 400
FULL_QUALITY = 85
FULL_QUALITY_FALLBACK = 75  # used if Q=85 output exceeds 1MB
FULL_MAX_BYTES = 1_000_000  # 1MB


def _save_full_sync(src: Path, dest: Path) -> None:
    """Resize src to max-side 2560px and save as JPEG. Blocking."""
    import pyvips

    dest.parent.mkdir(parents=True, exist_ok=True)
    img = pyvips.Image.thumbnail(
        str(src), FULL_MAX_SIDE, height=FULL_MAX_SIDE, size=pyvips.Size.DOWN
    )
    img.jpegsave(str(dest), Q=FULL_QUALITY, strip=True)
    if dest.stat().st_size > FULL_MAX_BYTES:
        # Reload from src: pyvips uses sequential (streaming) access by default,
        # so the pipeline is exhausted after the first jpegsave — calling it again
        # on the same img causes "out of order read". Re-thumbnail from source instead.
        img = pyvips.Image.thumbnail(
            str(src), FULL_MAX_SIDE, height=FULL_MAX_SIDE, size=pyvips.Size.DOWN
        )
        img.jpegsave(str(dest), Q=FULL_QUALITY_FALLBACK, strip=True)


def _save_thumb_sync(src: Path, dest: Path) -> None:
    """Resize src to max-side 400px and save as JPEG. Blocking."""
    import pyvips

    dest.parent.mkdir(parents=True, exist_ok=True)
    img = pyvips.Image.thumbnail(
        str(src), THUMB_MAX_SIDE, height=THUMB_MAX_SIDE, size=pyvips.Size.DOWN
    )
    img.jpegsave(str(dest), Q=FULL_QUALITY, strip=True)


def _optimize_one(src: Path, dest_full: Path, dest_thumb: Path) -> None:
    """Resize and compress a single JPEG to full and thumbnail sizes. Blocking."""
    _save_full_sync(src, dest_full)
    _save_thumb_sync(src, dest_thumb)


async def optimize_image_full(src: Path, dest: Path) -> None:
    """Async: resize src to max-side 2560px JPEG at dest. Skip if dest already exists."""
    if dest.exists() and dest.stat().st_size > 0:
        return
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, _save_full_sync, src, dest)


async def optimize_image_thumb(src: Path, dest: Path) -> None:
    """Async: resize src to max-side 400px JPEG at dest. Skip if dest already exists."""
    if dest.exists() and dest.stat().st_size > 0:
        return
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, _save_thumb_sync, src, dest)


async def optimize_album_images(
    album_slug: str,
    images_dir: Path,
    web_dir: Path,
    concurrency: int = 4,
) -> tuple[int, int, list[str]]:
    """Optimize all JPEGs for an album to web-ready full + thumbnail sizes.

    Returns (optimized, skipped, failed_ids) counts.
    """
    src_dir = images_dir / album_slug
    if not src_dir.exists():
        return 0, 0, []

    jpegs = sorted(src_dir.glob("*.jpg"))
    if not jpegs:
        return 0, 0, []

    semaphore = asyncio.Semaphore(concurrency)
    optimized = 0
    skipped = 0
    failed_ids: list[str] = []

    progress = Progress(
        TextColumn(f"[bold blue]Optimizing {album_slug}"),
        BarColumn(),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
    )

    async def _task(src: Path) -> bool | None:
        photo_id = src.stem
        dest_full = web_dir / album_slug / f"{photo_id}.jpg"
        dest_thumb = web_dir / album_slug / f"{photo_id}_thumb.jpg"
        if dest_full.exists() and dest_full.stat().st_size > 0 \
                and dest_thumb.exists() and dest_thumb.stat().st_size > 0:
            return False  # skipped
        async with semaphore:
            try:
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, _optimize_one, src, dest_full, dest_thumb)
                return True  # optimized
            except Exception as exc:
                _console.print(f"[yellow]  Warning: could not optimize {src.name}: {exc}[/yellow]")
                failed_ids.append(src.stem)
                return None  # failed

    with progress:
        task_id = progress.add_task("optimize", total=len(jpegs))
        tasks = [_task(jpeg) for jpeg in jpegs]
        for coro in asyncio.as_completed(tasks):
            result = await coro
            if result is True:
                optimized += 1
            elif result is False:
                skipped += 1
            progress.advance(task_id)

    return optimized, skipped, failed_ids


async def optimize_all_images(images_dir: Path, web_dir: Path, concurrency: int = 4) -> None:
    """Optimize all downloaded album JPEGs to web-ready sizes."""
    if not images_dir.exists():
        _console.print(f"[yellow]Images directory {images_dir} does not exist.[/yellow]")
        return

    album_dirs = sorted(d for d in images_dir.iterdir() if d.is_dir())
    if not album_dirs:
        _console.print("[yellow]No album directories found.[/yellow]")
        return

    _console.print(f"Optimizing [cyan]{len(album_dirs)}[/cyan] albums...\n")

    total_optimized = 0
    total_skipped = 0

    for album_dir in album_dirs:
        optimized, skipped, _ = await optimize_album_images(
            album_dir.name, images_dir, web_dir, concurrency
        )
        total_optimized += optimized
        total_skipped += skipped
        if optimized:
            _console.print(
                f"  [green]{album_dir.name}:[/green] {optimized} optimized, {skipped} skipped"
            )

    _console.print(
        f"\n[bold green]Done.[/bold green] "
        f"{total_optimized} optimized, {total_skipped} already existed."
    )
