"""Probe Flickr API endpoints and dump raw JSON responses."""

import argparse
import json
import sys
from pathlib import Path

from cca_archive.config import get_settings
from cca_archive.flickr_client import FlickrClient

OUTPUT_DIR = Path("research/sample_output")


def _check_settings():
    """Validate that required settings are available."""
    try:
        settings = get_settings()
    except Exception as e:
        print(
            "ERROR: Could not load settings. Make sure a .env file exists in the "
            "project root with the following keys:\n"
            "  FLICKR_API_KEY=...\n"
            "  FLICKR_API_SECRET=...\n"
            "  FLICKR_USER_ID=...\n"
            f"\nDetails: {e}",
            file=sys.stderr,
        )
        sys.exit(1)

    missing = []
    if not settings.flickr_api_key:
        missing.append("FLICKR_API_KEY")
    if not settings.flickr_api_secret:
        missing.append("FLICKR_API_SECRET")
    if not settings.flickr_user_id:
        missing.append("FLICKR_USER_ID")

    if missing:
        print(
            f"ERROR: Missing required environment variables: {', '.join(missing)}\n"
            "Add them to your .env file and try again.",
            file=sys.stderr,
        )
        sys.exit(1)

    return settings


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Probe Flickr API endpoints and dump raw JSON responses."
    )
    parser.add_argument(
        "--album-id",
        type=str,
        default=None,
        help="Specific album ID to inspect. If omitted, uses the first album.",
    )
    args = parser.parse_args()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    settings = _check_settings()
    client = FlickrClient(settings)

    # Dump album list
    print("Fetching album list...")
    albums = client.get_all_albums()
    with open(OUTPUT_DIR / "albums_list.json", "w") as f:
        json.dump(albums, f, indent=2)
    print(f"  Saved {len(albums)} albums to albums_list.json")

    # Determine which album to inspect
    album_id = args.album_id
    if album_id is None:
        if not albums:
            print("No albums found.")
            return
        album_id = str(albums[0]["id"])
        print(f"\nUsing first album: {album_id}")
    else:
        print(f"\nUsing specified album: {album_id}")

    # Dump album info and photos
    print(f"Fetching info for album {album_id}...")
    info = client.get_album_info(album_id)
    with open(OUTPUT_DIR / "album_info_sample.json", "w") as f:
        json.dump(info, f, indent=2)

    print(f"Fetching photos for album {album_id}...")
    photos = client.get_album_photos(album_id)
    with open(OUTPUT_DIR / "album_photos_sample.json", "w") as f:
        json.dump(photos[:5], f, indent=2)  # Just first 5
    print(f"  Saved {len(photos)} photos (first 5 to file)")


if __name__ == "__main__":
    main()
