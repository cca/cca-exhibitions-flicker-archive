"""Convert downloaded JPEGs to pyramidal tiled TIFFs for IIIF serving."""

import asyncio
from pathlib import Path

from rich.console import Console
from rich.progress import BarColumn, MofNCompleteColumn, Progress, TextColumn, TimeElapsedColumn

_console = Console()


def _convert_one(src: Path, dest: Path) -> None:
    """Convert a single JPEG to a pyramidal tiled TIFF. Blocking."""
    import pyvips

    dest.parent.mkdir(parents=True, exist_ok=True)
    img = pyvips.Image.new_from_file(str(src), access="sequential")
    img.tiffsave(
        str(dest),
        tile=True,
        pyramid=True,
        compression="jpeg",
        tile_width=256,
        tile_height=256,
        Q=85,
    )


async def convert_album_tiffs(
    album_slug: str,
    images_dir: Path,
    tiffs_dir: Path,
    concurrency: int = 4,
) -> tuple[int, int]:
    """Convert all JPEGs for an album to pyramidal TIFFs.

    Returns (converted, skipped) counts.
    """
    src_dir = images_dir / album_slug
    if not src_dir.exists():
        return 0, 0

    jpegs = sorted(src_dir.glob("*.jpg"))
    if not jpegs:
        return 0, 0

    semaphore = asyncio.Semaphore(concurrency)
    converted = 0
    skipped = 0

    progress = Progress(
        TextColumn(f"[bold blue]Converting {album_slug}"),
        BarColumn(),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
    )

    async def _task(src: Path) -> bool:
        dest = tiffs_dir / album_slug / src.with_suffix(".tif").name
        if dest.exists() and dest.stat().st_size > 0:
            return False  # skipped
        async with semaphore:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, _convert_one, src, dest)
        return True  # converted

    with progress:
        task_id = progress.add_task("tiffs", total=len(jpegs))
        tasks = []
        for jpeg in jpegs:
            tasks.append(_task(jpeg))

        for coro in asyncio.as_completed(tasks):
            did_convert = await coro
            if did_convert:
                converted += 1
            else:
                skipped += 1
            progress.advance(task_id)

    return converted, skipped


async def convert_all_tiffs(images_dir: Path, tiffs_dir: Path, concurrency: int = 4) -> None:
    """Convert all downloaded album JPEGs to pyramidal TIFFs."""
    if not images_dir.exists():
        _console.print(f"[yellow]Images directory {images_dir} does not exist.[/yellow]")
        return

    album_dirs = sorted(d for d in images_dir.iterdir() if d.is_dir())
    if not album_dirs:
        _console.print("[yellow]No album directories found.[/yellow]")
        return

    _console.print(f"Converting [cyan]{len(album_dirs)}[/cyan] albums to pyramidal TIFFs...\n")

    total_converted = 0
    total_skipped = 0

    for album_dir in album_dirs:
        converted, skipped = await convert_album_tiffs(
            album_dir.name, images_dir, tiffs_dir, concurrency
        )
        total_converted += converted
        total_skipped += skipped
        if converted:
            _console.print(f"  [green]{album_dir.name}:[/green] {converted} converted, {skipped} skipped")

    _console.print(
        f"\n[bold green]Done.[/bold green] "
        f"{total_converted} converted, {total_skipped} already existed."
    )
