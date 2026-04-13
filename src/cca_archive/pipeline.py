"""Main pipeline orchestrator and CLI entry point."""

import argparse
import asyncio
import csv as csv_module
import sys
from pathlib import Path

from pydantic import ValidationError
from rich.console import Console
from rich.table import Table
from slugify import slugify

from .config import Settings, get_settings
from .csv_export import export_album_csv
from .downloader import download_photos
from .flickr_client import FlickrClient, extract_photographer_from_photos, parse_album_url
from .gcs_uploader import upload_album_images_to_gcs, upload_csv_to_gcs
from .ia_uploader import upload_album_to_ia
from .llm import extract_exhibition_metadata
from .manifest import get_failed_llm_slugs, load_manifest, save_manifest, update_stage
from .models import AlbumRecord

console = Console()


def _album_title(a: dict) -> str:
    """Extract title string from a raw album dict."""
    title = a.get("title", {})
    if isinstance(title, dict):
        title = title.get("_content", "")
    return str(title)


def _is_complete(album: dict, manifest: dict, existing_csvs: set[str]) -> bool:
    """Return True if the album has been fully processed.

    Uses manifest csv_export status when available; falls back to CSV existence
    for albums that predate the manifest (backward compat).
    """
    slug = slugify(_album_title(album))
    if slug in manifest:
        return manifest[slug].get("stages", {}).get("csv_export", {}).get("status") == "success"
    return slug in existing_csvs


async def process_album(
    album_id: str,
    client: FlickrClient,
    skip_download: bool = False,
    skip_llm: bool = False,
    upload_ia: bool = False,
    upload_gcs: bool = False,
) -> int:
    """Process a single album: fetch data, extract metadata, download, export CSV.

    Returns the number of photos in the album.
    """
    settings = client.settings
    manifest = load_manifest(settings)

    console.print(f"\n[bold]Fetching album [cyan]{album_id}[/cyan]...[/bold]")
    album = client.build_album_record(album_id)
    console.print(f"  Title: [green]{album.title}[/green]")
    console.print(f"  Photos: {album.photo_count}")

    slug = slugify(album.title)

    # LLM extraction
    llm_status = "skipped"
    llm_error = None
    if not skip_llm and album.description:
        console.print("  [bold]Extracting exhibition metadata via LLM...[/bold]")
        try:
            album.exhibition = await extract_exhibition_metadata(
                description=album.description,
                album_title=album.title,
                settings=settings,
            )
            llm_status = "success"
            if album.exhibition:
                console.print(f"  Exhibition: [green]{album.exhibition.exhibition_title}[/green]")
                if album.exhibition.artists:
                    console.print(f"  Artists: {', '.join(album.exhibition.artists)}")
        except Exception as e:
            llm_status = "failed"
            llm_error = str(e)
            console.print(f"  [red]LLM extraction failed: {e}[/red]")
    update_stage(manifest, slug, album_id, album.title, "llm_extraction", llm_status, error=llm_error)
    save_manifest(manifest, settings)

    # Backfill photographer from photo titles/descriptions if LLM didn't find one
    if album.exhibition and not album.exhibition.photographer and album.photos:
        photographer = extract_photographer_from_photos(album.photos)
        if photographer:
            album.exhibition.photographer = photographer
            console.print(f"  Photographer (from photos): [green]{photographer}[/green]")

    # Download images
    if skip_download:
        dl_status = "skipped"
    elif not album.photos:
        dl_status = "success"
    else:
        dest = settings.images_dir / slug
        console.print(f"  [bold]Downloading images to {dest}...[/bold]")
        album.photos = await download_photos(
            album.photos, dest, concurrency=settings.download_concurrency
        )
        dl_status = "success"
    downloaded = sum(1 for p in album.photos if p.local_filename)
    total = len(album.photos)
    update_stage(manifest, slug, album_id, album.title, "image_download", dl_status,
                 downloaded=downloaded, total=total)
    save_manifest(manifest, settings)

    # Upload to Internet Archive
    ia_status = "not_attempted"
    ia_error = None
    if upload_ia:
        try:
            album.ia_identifier = await upload_album_to_ia(
                album, settings.images_dir, settings
            )
            ia_status = "success"
        except Exception as e:
            ia_status = "failed"
            ia_error = str(e)
            console.print(f"  [red]IA upload failed: {e}[/red]")
    update_stage(manifest, slug, album_id, album.title, "ia_upload", ia_status, error=ia_error)
    save_manifest(manifest, settings)

    # Export CSV
    csv_path = None
    csv_status = "failed"
    try:
        csv_path = export_album_csv(album, settings.csv_dir)
        csv_status = "success"
        console.print(f"  [bold green]CSV exported:[/bold green] {csv_path}")
    finally:
        update_stage(
            manifest, slug, album_id, album.title, "csv_export", csv_status,
            path=str(csv_path) if csv_path else None,
        )
        save_manifest(manifest, settings)

    # Upload to GCS
    gcs_status = "not_attempted"
    gcs_error = None
    if upload_gcs:
        try:
            await upload_album_images_to_gcs(album, settings.images_dir, settings)
            await upload_csv_to_gcs(csv_path, settings)
            gcs_status = "success"
        except Exception as e:
            gcs_status = "failed"
            gcs_error = str(e)
            console.print(f"  [red]GCS upload failed: {e}[/red]")
    update_stage(manifest, slug, album_id, album.title, "gcs_upload", gcs_status, error=gcs_error)
    save_manifest(manifest, settings)

    return album.photo_count


async def process_all_albums(
    client: FlickrClient,
    skip_download: bool = False,
    skip_llm: bool = False,
    skip_existing: bool = False,
    limit: int | None = None,
    upload_ia: bool = False,
    upload_gcs: bool = False,
    retry_llm_failures: bool = False,
) -> None:
    """Process all albums for the configured Flickr user."""
    settings = client.settings
    console.print("[bold]Fetching all albums...[/bold]")
    albums = client.get_all_albums()
    console.print(f"Found [cyan]{len(albums)}[/cyan] albums total\n")

    if retry_llm_failures:
        manifest = load_manifest(settings)
        failed_slugs = get_failed_llm_slugs(manifest)
        if not failed_slugs:
            console.print("[yellow]No albums with failed LLM extraction found in manifest.[/yellow]")
            return
        albums = [a for a in albums if slugify(_album_title(a)) in failed_slugs]
        skip_download = True  # LLM + CSV rewrite only
        console.print(
            f"Retrying LLM extraction for [cyan]{len(albums)}[/cyan] album(s) "
            f"with prior failures\n"
        )
    elif skip_existing:
        manifest = load_manifest(settings)
        existing_csvs = {p.stem for p in settings.csv_dir.glob("*.csv")}
        before = len(albums)
        albums = [a for a in albums if not _is_complete(a, manifest, existing_csvs)]
        console.print(
            f"Skipping {before - len(albums)} already-processed albums, "
            f"[cyan]{len(albums)}[/cyan] remaining\n"
        )

    # Apply limit
    if limit is not None and limit < len(albums):
        albums = albums[:limit]
        console.print(f"Limited to first [cyan]{limit}[/cyan] albums\n")

    # Print summary table
    table = Table(title="Albums to Process")
    table.add_column("ID", style="dim")
    table.add_column("Title")
    table.add_column("Photos", justify="right")
    for a in albums:
        table.add_row(str(a["id"]), _album_title(a), str(a.get("photos", "?")))
    console.print(table)

    total_albums_processed = 0
    total_photos = 0
    total_failures = 0

    for a in albums:
        album_id = str(a["id"])
        try:
            photo_count = await process_album(
                album_id, client, skip_download, skip_llm, upload_ia, upload_gcs
            )
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


def _load_album_record_from_csv(csv_path: Path) -> AlbumRecord:
    """Build a minimal AlbumRecord from the first row of a CSV (title + IDs only needed)."""
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv_module.DictReader(f)
        row = next(reader)
    return AlbumRecord(
        album_id=row["album_id"],
        album_url=row["album_url"],
        title=row["album_title"],
        ia_identifier=row.get("ia_identifier") or None,
    )


def backfill_manifest(settings: Settings) -> None:
    """Populate manifest.json from existing CSVs. Idempotent — skips albums already present."""
    manifest = load_manifest(settings)

    if not settings.csv_dir.exists():
        console.print(f"[yellow]CSV directory {settings.csv_dir} does not exist.[/yellow]")
        return

    csv_files = sorted(settings.csv_dir.glob("*.csv"))
    if not csv_files:
        console.print("[yellow]No CSV files found in output/csv/.[/yellow]")
        return

    backfilled = 0
    skipped = 0

    for csv_path in csv_files:
        slug = csv_path.stem

        if slug in manifest:
            skipped += 1
            continue

        try:
            with open(csv_path, newline="", encoding="utf-8") as f:
                reader = csv_module.DictReader(f)
                rows = list(reader)
        except Exception as e:
            console.print(f"  [red]Failed to read {csv_path.name}: {e}[/red]")
            continue

        if not rows:
            album_id = ""
            album_title = slug
            has_local = False
            has_exhibition = False
            has_ia = False
        else:
            first = rows[0]
            album_id = first.get("album_id", "")
            album_title = first.get("album_title", slug)
            has_local = any(r.get("local_filename", "") for r in rows)
            has_exhibition = bool(first.get("exhibition_title", ""))
            has_ia = bool(first.get("ia_identifier", ""))

        llm_status = "success" if has_exhibition else "unknown"
        dl_status = "success" if has_local else "skipped"
        ia_status = "success" if has_ia else "not_attempted"

        update_stage(manifest, slug, album_id, album_title, "llm_extraction", llm_status, error=None)
        update_stage(manifest, slug, album_id, album_title, "image_download", dl_status,
                     downloaded=0, total=0)
        update_stage(manifest, slug, album_id, album_title, "csv_export", "success",
                     path=str(csv_path))
        update_stage(manifest, slug, album_id, album_title, "ia_upload", ia_status, error=None)
        update_stage(manifest, slug, album_id, album_title, "gcs_upload", "not_attempted",
                     error=None)
        backfilled += 1

    save_manifest(manifest, settings)
    console.print(
        f"Backfilled [cyan]{backfilled}[/cyan] album(s), "
        f"skipped [cyan]{skipped}[/cyan] (already had manifest entry)"
    )


async def sync_command(upload_ia: bool, upload_gcs: bool, settings) -> None:
    """Sync existing output/ dirs to configured storage backends."""
    images_dir = settings.images_dir
    if not images_dir.exists():
        console.print(f"[red]Images directory {images_dir} does not exist.[/red]")
        return

    album_dirs = sorted(d for d in images_dir.iterdir() if d.is_dir())
    if not album_dirs:
        console.print("[yellow]No album directories found in output/images/.[/yellow]")
        return

    console.print(f"Found [cyan]{len(album_dirs)}[/cyan] album directories to sync.\n")

    for album_dir in album_dirs:
        slug = album_dir.name
        csv_path = settings.csv_dir / f"{slug}.csv"
        console.print(f"\n[bold]Syncing [cyan]{slug}[/cyan]...[/bold]")

        if not csv_path.exists():
            console.print(f"  [yellow]No CSV for {slug}, skipping[/yellow]")
            continue

        try:
            album = _load_album_record_from_csv(csv_path)
        except Exception as e:
            console.print(f"  [red]Failed to load CSV for {slug}: {e}[/red]")
            continue

        if upload_ia:
            try:
                await upload_album_to_ia(album, images_dir, settings)
            except Exception as e:
                console.print(f"  [red]IA upload failed for {slug}: {e}[/red]")

        if upload_gcs:
            try:
                await upload_album_images_to_gcs(album, images_dir, settings)
                await upload_csv_to_gcs(csv_path, settings)
            except Exception as e:
                console.print(f"  [red]GCS upload failed for {slug}: {e}[/red]")


def _run_sync_command(argv: list[str]) -> None:
    sync_parser = argparse.ArgumentParser(
        prog="cca-archive sync",
        description="Sync existing output/ to storage backends without re-running the pipeline",
    )
    sync_parser.add_argument("--ia", action="store_true", help="Upload to Internet Archive")
    sync_parser.add_argument("--gcs", action="store_true", help="Upload to Google Cloud Storage")
    args = sync_parser.parse_args(argv)

    # Default: all configured backends
    upload_ia = args.ia
    upload_gcs = args.gcs
    if not upload_ia and not upload_gcs:
        upload_ia = True
        upload_gcs = True

    try:
        settings = get_settings()
    except ValidationError as e:
        console.print(f"[red]Settings error:[/red] {e}\n[yellow]Tip: set SKIP_LLM=true in .env to run sync without LLM API keys[/yellow]")
        sys.exit(1)

    asyncio.run(sync_command(upload_ia, upload_gcs, settings))


def _run_backfill_manifest_command(argv: list[str]) -> None:
    parser = argparse.ArgumentParser(
        prog="cca-archive backfill-manifest",
        description="Populate manifest.json from existing CSVs (one-off, idempotent)",
    )
    parser.parse_args(argv)  # no flags; just validate no unexpected args

    try:
        settings = get_settings()
    except ValidationError as e:
        console.print(f"[red]Settings error:[/red] {e}\n[yellow]Tip: set SKIP_LLM=true in .env to run backfill-manifest without LLM API keys[/yellow]")
        sys.exit(1)

    backfill_manifest(settings)


def main() -> None:
    # Fast-path: dispatch subcommands before full parser runs
    if len(sys.argv) > 1 and sys.argv[1] == "sync":
        _run_sync_command(sys.argv[2:])
        return
    if len(sys.argv) > 1 and sys.argv[1] == "backfill-manifest":
        _run_backfill_manifest_command(sys.argv[2:])
        return

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
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum number of albums to process (useful with --all)",
    )
    parser.add_argument(
        "--upload-ia",
        action="store_true",
        help="Upload images to Internet Archive after download",
    )
    parser.add_argument(
        "--upload-gcs",
        action="store_true",
        help="Upload images and CSV to Google Cloud Storage after download",
    )

    skip_group = parser.add_mutually_exclusive_group()
    skip_group.add_argument(
        "--skip-existing",
        action="store_true",
        help="Skip albums that already have a successful CSV export in the manifest (or CSV file for pre-manifest albums)",
    )
    skip_group.add_argument(
        "--retry-llm-failures",
        action="store_true",
        help="Re-run LLM extraction and CSV export for albums where LLM previously failed",
    )

    args = parser.parse_args()

    if not args.album_url and not args.all and not args.retry_llm_failures:
        parser.error("Provide an album URL, use --all, or use --retry-llm-failures")

    settings = get_settings()
    client = FlickrClient(settings)

    if args.all or args.retry_llm_failures:
        asyncio.run(process_all_albums(
            client,
            skip_download=args.skip_download,
            skip_llm=args.skip_llm,
            skip_existing=args.skip_existing,
            limit=args.limit,
            upload_ia=args.upload_ia,
            upload_gcs=args.upload_gcs,
            retry_llm_failures=args.retry_llm_failures,
        ))
    else:
        album_id = parse_album_url(args.album_url)
        asyncio.run(process_album(
            album_id, client, args.skip_download, args.skip_llm,
            upload_ia=args.upload_ia,
            upload_gcs=args.upload_gcs,
        ))


if __name__ == "__main__":
    main()
