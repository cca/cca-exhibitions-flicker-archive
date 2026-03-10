"""Flickr API wrapper."""

import re
from datetime import datetime
from typing import Any, Optional

import flickrapi

from .config import Settings
from .models import AlbumRecord, PhotoRecord

# Extras to request from Flickr API to avoid per-photo API calls
PHOTO_EXTRAS = (
    "description,date_taken,date_upload,views,tags,"
    "license,url_o,url_l,url_m,original_format"
)

# License map from Flickr license IDs
LICENSE_MAP = {
    "0": "All Rights Reserved",
    "1": "CC BY-NC-SA 2.0",
    "2": "CC BY-NC 2.0",
    "3": "CC BY-NC-ND 2.0",
    "4": "CC BY 2.0",
    "5": "CC BY-SA 2.0",
    "6": "CC BY-ND 2.0",
    "7": "No known copyright restrictions",
    "8": "US Government Work",
    "9": "CC0 1.0",
    "10": "PDM 1.0",
}


def parse_album_url(url: str) -> str:
    """Extract album/photoset ID from a Flickr album URL.

    Supports URLs like:
        https://www.flickr.com/photos/user/albums/72177720312345678
        https://www.flickr.com/photos/user/sets/72177720312345678
    """
    match = re.search(r"(?:albums|sets)/(\d+)", url)
    if match:
        return match.group(1)
    # Maybe it's just the raw ID
    if url.strip().isdigit():
        return url.strip()
    raise ValueError(f"Cannot extract album ID from: {url}")


class FlickrClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.api = flickrapi.FlickrAPI(
            settings.flickr_api_key,
            settings.flickr_api_secret,
            format="parsed-json",
        )
        self.user_id = settings.flickr_user_id

    def get_all_albums(self) -> list[dict[str, Any]]:
        """Fetch all albums/photosets for the configured user."""
        albums: list[dict[str, Any]] = []
        page = 1
        while True:
            resp = self.api.photosets.getList(
                user_id=self.user_id,
                page=page,
                per_page=500,
            )
            photosets = resp["photosets"]
            albums.extend(photosets["photoset"])
            if page >= photosets["pages"]:
                break
            page += 1
        return albums

    def get_album_info(self, album_id: str) -> dict[str, Any]:
        """Fetch album metadata."""
        resp = self.api.photosets.getInfo(
            photoset_id=album_id,
            user_id=self.user_id,
        )
        return resp["photoset"]

    def get_album_photos(self, album_id: str) -> list[dict[str, Any]]:
        """Fetch all photos in an album with extras, handling pagination."""
        photos: list[dict[str, Any]] = []
        page = 1
        while True:
            resp = self.api.photosets.getPhotos(
                photoset_id=album_id,
                user_id=self.user_id,
                extras=PHOTO_EXTRAS,
                page=page,
                per_page=500,
            )
            photoset = resp["photoset"]
            photos.extend(photoset["photo"])
            if page >= photoset["pages"]:
                break
            page += 1
        return photos

    def build_album_record(self, album_id: str) -> AlbumRecord:
        """Build a full AlbumRecord from API data."""
        info = self.get_album_info(album_id)
        raw_photos = self.get_album_photos(album_id)

        title = _text(info.get("title"))
        description = _text(info.get("description"))

        photos = [_parse_photo(p) for p in raw_photos]

        return AlbumRecord(
            album_id=album_id,
            album_url=f"https://www.flickr.com/photos/{self.user_id}/albums/{album_id}",
            title=title,
            description=description,
            photo_count=int(info.get("count_photos", info.get("photos", 0))),
            date_created=_ts(info.get("date_create")),
            date_updated=_ts(info.get("date_update")),
            photos=photos,
        )


def _text(val: Any) -> str:
    """Extract text from Flickr's nested {'_content': '...'} pattern."""
    if isinstance(val, dict):
        return val.get("_content", "")
    return str(val) if val else ""


def _ts(val: Any) -> Optional[datetime]:
    """Convert Unix timestamp string to datetime."""
    if val is None:
        return None
    try:
        return datetime.fromtimestamp(int(val))
    except (ValueError, TypeError):
        return None


def _parse_photo(data: dict[str, Any]) -> PhotoRecord:
    """Parse a photo dict from the Flickr API into a PhotoRecord."""
    desc = data.get("description", {})
    if isinstance(desc, dict):
        desc = desc.get("_content", "")

    tags_str = data.get("tags", "")
    tags = tags_str.split() if isinstance(tags_str, str) and tags_str else []

    date_taken = None
    if data.get("datetaken"):
        try:
            date_taken = datetime.strptime(data["datetaken"], "%Y-%m-%d %H:%M:%S")
        except ValueError:
            pass

    return PhotoRecord(
        photo_id=str(data["id"]),
        title=data.get("title"),
        description=desc or None,
        tags=tags,
        date_taken=date_taken,
        date_uploaded=_ts(data.get("dateupload")),
        views=int(data.get("views", 0)),
        license=LICENSE_MAP.get(str(data.get("license", "")), None),
        original_url=data.get("url_o"),
        large_url=data.get("url_l"),
        medium_url=data.get("url_m"),
    )
