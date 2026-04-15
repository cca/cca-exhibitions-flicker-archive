"""Upload album images and CSVs to Google Cloud Storage."""

import asyncio
from pathlib import Path

from google.cloud import storage
from rich.console import Console
from slugify import slugify

from .config import Settings
from .models import AlbumRecord

console = Console()

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".gif", ".tif", ".tiff", ".webp"}


def _make_client(settings: Settings) -> storage.Client:
    if settings.gcs_credentials_file:
        return storage.Client.from_service_account_json(settings.gcs_credentials_file)
    return storage.Client()


def _upload_files_sync(
    files: list[tuple[Path, str]],
    bucket_name: str,
    settings: Settings,
    content_type: str | None = None,
    cache_control: str | None = None,
) -> None:
    """Upload a list of (local_path, gcs_object_name) pairs synchronously."""
    client = _make_client(settings)
    bucket = client.bucket(bucket_name)
    for local_path, gcs_name in files:
        blob = bucket.blob(gcs_name)
        if content_type:
            blob.content_type = content_type
        if cache_control:
            blob.cache_control = cache_control
        blob.upload_from_filename(str(local_path))


async def upload_album_images_to_gcs(
    album: AlbumRecord, image_dir: Path, settings: Settings
) -> None:
    """Upload all album images to GCS under images/{slug}/."""
    album_slug = slugify(album.title)
    album_image_dir = image_dir / album_slug

    if not album_image_dir.exists():
        console.print(f"  [yellow]No images directory at {album_image_dir}, skipping GCS upload[/yellow]")
        return

    files_to_upload = [
        (f, f"images/{album_slug}/{f.name}")
        for f in album_image_dir.iterdir()
        if f.is_file() and f.suffix.lower() in IMAGE_SUFFIXES
    ]

    if not files_to_upload:
        console.print(f"  [yellow]No image files found in {album_image_dir}, skipping GCS upload[/yellow]")
        return

    console.print(
        f"  [bold]Uploading {len(files_to_upload)} images to GCS "
        f"bucket [cyan]{settings.gcs_bucket}[/cyan]...[/bold]"
    )

    loop = asyncio.get_event_loop()
    await loop.run_in_executor(
        None,
        lambda: _upload_files_sync(files_to_upload, settings.gcs_bucket, settings),
    )

    console.print(
        f"  [bold green]Uploaded images to GCS:[/bold green] "
        f"gs://{settings.gcs_bucket}/images/{album_slug}/"
    )


async def upload_album_tiffs_to_gcs(
    album: AlbumRecord, tiffs_dir: Path, settings: Settings
) -> None:
    """Upload all album TIFFs to GCS under tiffs/{slug}/."""
    album_slug = slugify(album.title)
    album_tiffs_dir = tiffs_dir / album_slug

    if not album_tiffs_dir.exists():
        console.print(f"  [yellow]No TIFFs directory at {album_tiffs_dir}, skipping TIFF GCS upload[/yellow]")
        return

    files_to_upload = [
        (f, f"tiffs/{album_slug}/{f.name}")
        for f in album_tiffs_dir.iterdir()
        if f.is_file() and f.suffix.lower() in {".tif", ".tiff"}
    ]

    if not files_to_upload:
        console.print(f"  [yellow]No TIFF files found in {album_tiffs_dir}, skipping TIFF GCS upload[/yellow]")
        return

    console.print(
        f"  [bold]Uploading {len(files_to_upload)} TIFFs to GCS "
        f"bucket [cyan]{settings.gcs_bucket}[/cyan]...[/bold]"
    )

    loop = asyncio.get_event_loop()
    await loop.run_in_executor(
        None,
        lambda: _upload_files_sync(files_to_upload, settings.gcs_bucket, settings),
    )

    console.print(
        f"  [bold green]Uploaded TIFFs to GCS:[/bold green] "
        f"gs://{settings.gcs_bucket}/tiffs/{album_slug}/"
    )


async def upload_album_web_images_to_gcs(
    album: AlbumRecord, web_dir: Path, settings: Settings
) -> None:
    """Upload optimized web images to GCS under web/{slug}/ with long-lived cache headers."""
    album_slug = slugify(album.title)
    album_web_dir = web_dir / album_slug

    if not album_web_dir.exists():
        console.print(f"  [yellow]No web images directory at {album_web_dir}, skipping GCS upload[/yellow]")
        return

    files_to_upload = [
        (f, f"web/{album_slug}/{f.name}")
        for f in album_web_dir.iterdir()
        if f.is_file() and f.suffix.lower() == ".jpg"
    ]

    if not files_to_upload:
        console.print(f"  [yellow]No web image files found in {album_web_dir}, skipping GCS upload[/yellow]")
        return

    console.print(
        f"  [bold]Uploading {len(files_to_upload)} web images to GCS "
        f"bucket [cyan]{settings.gcs_bucket}[/cyan]...[/bold]"
    )

    loop = asyncio.get_event_loop()
    await loop.run_in_executor(
        None,
        lambda: _upload_files_sync(
            files_to_upload,
            settings.gcs_bucket,
            settings,
            content_type="image/jpeg",
            cache_control="public, max-age=31536000",
        ),
    )

    console.print(
        f"  [bold green]Uploaded web images to GCS:[/bold green] "
        f"gs://{settings.gcs_bucket}/web/{album_slug}/"
    )


async def upload_csv_to_gcs(csv_path: Path, settings: Settings) -> None:
    """Upload a single CSV file to GCS under csv/."""
    if not csv_path.exists():
        console.print(f"  [yellow]CSV not found at {csv_path}, skipping GCS upload[/yellow]")
        return

    gcs_name = f"csv/{csv_path.name}"
    console.print(f"  [bold]Uploading CSV to GCS as [cyan]{gcs_name}[/cyan]...[/bold]")

    loop = asyncio.get_event_loop()
    await loop.run_in_executor(
        None,
        lambda: _upload_files_sync([(csv_path, gcs_name)], settings.gcs_bucket, settings),
    )

    console.print(
        f"  [bold green]Uploaded CSV to GCS:[/bold green] "
        f"gs://{settings.gcs_bucket}/{gcs_name}"
    )


def _update_manifest_sync(settings: Settings, slug: str) -> None:
    import json
    from datetime import datetime, timezone
    from google.api_core.exceptions import NotFound

    client = _make_client(settings)
    bucket = client.bucket(settings.gcs_bucket)
    blob = bucket.blob("csv/manifest.json")
    try:
        data = json.loads(blob.download_as_bytes())
    except NotFound:
        data = {"slugs": []}
    slugs: list[str] = data.get("slugs", [])
    if slug not in slugs:
        slugs.append(slug)
    blob.upload_from_string(
        json.dumps({"slugs": slugs, "updated": datetime.now(timezone.utc).isoformat()}, indent=2),
        content_type="application/json",
    )


async def update_gcs_manifest(settings: Settings, slug: str) -> None:
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, lambda: _update_manifest_sync(settings, slug))
    console.print(f"  [bold green]Manifest updated:[/bold green] gs://{settings.gcs_bucket}/csv/manifest.json")
