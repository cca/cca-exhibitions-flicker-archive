"""Main pipeline orchestrator and CLI entry point."""

import argparse
import asyncio
import sys

from rich.console import Console
from rich.table import Table
from slugify import slugify

from .config import get_settings
from .csv_export import export_album_csv
from .downloader import download_photos
from .flickr_client import FlickrClient, extract_photographer_from_photos, parse_album_url
from .llm import extract_exhibition_metadata

console = Console()


async def process_album(
    album_id: str,
    client: FlickrClient,
    skip_download: bool = False,
    skip_llm: bool = False,
) -> int:
    """Process a single album: fetch data, extract metadata, download, export CSV.

    Returns the number of photos in the album.
    """
    settings = client.settings

    console.print(f"\n[bold]Fetching album [cyan]{album_id}[/cyan]...[/bold]")
    album = client.build_album_record(album_id)
    console.print(f"  Title: [green]{album.title}[/green]")
    console.print(f"  Photos: {album.photo_count}")

    # LLM extraction
    if not skip_llm and album.description:
        console.print("  [bold]Extracting exhibition metadata via LLM...[/bold]")
        try:
            album.exhibition = await extract_exhibition_metadata(
                description=album.description,
                album_title=album.title,
                settings=settings,
            )
            if album.exhibition:
                console.print(f"  Exhibition: [green]{album.exhibition.exhibition_title}[/green]")
                if album.exhibition.artists:
                    console.print(f"  Artists: {', '.join(album.exhibition.artists)}")
        except Exception as e:
            console.print(f"  [red]LLM extraction failed: {e}[/red]")

    # Backfill photographer from photo titles/descriptions if LLM didn't find one
    if album.exhibition and not album.exhibition.photographer and album.photos:
        photographer = extract_photographer_from_photos(album.photos)
        if photographer:
            album.exhibition.photographer = photographer
            console.print(f"  Photographer (from photos): [green]{photographer}[/green]")

    # Download images
    if not skip_download and album.photos:
        album_slug = slugify(album.title)
        dest = settings.images_dir / album_slug
        console.print(f"  [bold]Downloading images to {dest}...[/bold]")
        album.photos = await download_photos(
            album.photos, dest, concurrency=settings.download_concurrency
        )

    # Export CSV
    csv_path = export_album_csv(album, settings.csv_dir)
    console.print(f"  [bold green]CSV exported:[/bold green] {csv_path}")

    return album.photo_count


async def process_all_albums(
    client: FlickrClient,
    skip_download: bool = False,
    skip_llm: bool = False,
) -> None:
    """Process all albums for the configured Flickr user."""
    console.print("[bold]Fetching all albums...[/bold]")
    albums = client.get_all_albums()
    console.print(f"Found [cyan]{len(albums)}[/cyan] albums\n")

    # Print summary table
    table = Table(title="Albums")
    table.add_column("ID", style="dim")
    table.add_column("Title")
    table.add_column("Photos", justify="right")
    for a in albums:
        title = a.get("title", {})
        if isinstance(title, dict):
            title = title.get("_content", "")
        table.add_row(str(a["id"]), str(title), str(a.get("photos", "?")))
    console.print(table)

    total_albums_processed = 0
    total_photos = 0
    total_failures = 0

    for a in albums:
        album_id = str(a["id"])
        try:
            photo_count = await process_album(album_id, client, skip_download, skip_llm)
            total_albums_processed += 1
            total_photos += photo_count
        except Exception as e:
            console.print(f"[red]Error processing album {album_id}: {e}[/red]")
            total_failures += 1
            continue

    # Print run summary
    summary = Table(title="Run Summary")
    summary.add_column("Metric", style="bold")
    summary.add_column("Value", justify="right")
    summary.add_row("Albums processed", str(total_albums_processed))
    summary.add_row("Total photos", str(total_photos))
    summary.add_row("Failed albums", str(total_failures))
    console.print()
    console.print(summary)


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="cca-archive",
        description="Archive CCA Exhibitions Flickr albums",
    )
    parser.add_argument(
        "album_url",
        nargs="?",
        help="Flickr album URL or album ID to process",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Process all albums for the configured Flickr user",
    )
    parser.add_argument(
        "--skip-download",
        action="store_true",
        help="Skip image downloads (metadata and CSV only)",
    )
    parser.add_argument(
        "--skip-llm",
        action="store_true",
        help="Skip LLM metadata extraction",
    )

    args = parser.parse_args()

    if not args.album_url and not args.all:
        parser.error("Provide an album URL or use --all to process all albums")

    settings = get_settings()
    client = FlickrClient(settings)

    if args.all:
        asyncio.run(process_all_albums(client, args.skip_download, args.skip_llm))
    else:
        album_id = parse_album_url(args.album_url)
        asyncio.run(process_album(album_id, client, args.skip_download, args.skip_llm))


if __name__ == "__main__":
    main()
