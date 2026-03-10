"""Probe Flickr API endpoints and dump raw JSON responses."""

import json
from pathlib import Path

from cca_archive.config import get_settings
from cca_archive.flickr_client import FlickrClient

OUTPUT_DIR = Path("research/sample_output")


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    settings = get_settings()
    client = FlickrClient(settings)

    # Dump album list
    print("Fetching album list...")
    albums = client.get_all_albums()
    with open(OUTPUT_DIR / "albums_list.json", "w") as f:
        json.dump(albums, f, indent=2)
    print(f"  Saved {len(albums)} albums to albums_list.json")

    # Dump first album's info and photos
    if albums:
        first = albums[0]
        album_id = str(first["id"])
        print(f"\nFetching info for album {album_id}...")
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
