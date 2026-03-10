"""Flickr API wrapper."""

import functools
import re
import time
from datetime import datetime
from typing import Any, Optional

import flickrapi

from .config import Settings
from .models import AlbumRecord, PhotoRecord


class FlickrAPIError(Exception):
    """Raised when the Flickr API returns an error response."""

    def __init__(self, code: int | str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(f"Flickr API error {code}: {message}")


def _retry_api_call(max_retries: int = 3, base_delay: float = 1.0):
    """Decorator that retries Flickr API calls on transient errors.

    Retries on network errors, rate limiting, and server errors with
    exponential backoff.
    """

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_exc: Exception | None = None
            for attempt in range(max_retries + 1):
                try:
                    result = func(*args, **kwargs)
                    # Check for Flickr error responses
                    if isinstance(result, dict) and result.get("stat") != "ok":
                        code = result.get("code", "?")
                        msg = result.get("message", "Unknown error")
                        raise FlickrAPIError(code, msg)
                    return result
                except FlickrAPIError:
                    raise  # Don't retry on explicit API errors
                except (flickrapi.exceptions.FlickrError, OSError, ConnectionError) as exc:
                    last_exc = exc
                    if attempt < max_retries:
                        delay = base_delay * (2 ** attempt)
                        time.sleep(delay)
                    continue
            raise last_exc  # type: ignore[misc]

        return wrapper

    return decorator

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


_PHOTOGRAPHER_RE = re.compile(
    r"^(?:photo|photos|taken|photographed|images?\s+courtesy)\s+(?:by|of)\s+(.+?)\.?$",
    re.IGNORECASE,
)


def extract_photographer_from_photos(photos: list["PhotoRecord"]) -> str | None:
    """Extract photographer name from photo titles or descriptions.

    Many CCA albums use "Photo by Name" as the photo title or description
    rather than including the credit in the album description.
    Returns the photographer name if a consistent credit is found.
    """
    from collections import Counter

    candidates: Counter[str] = Counter()
    for photo in photos:
        for text in (photo.title, photo.description):
            if text:
                m = _PHOTOGRAPHER_RE.match(text.strip())
                if m:
                    candidates[m.group(1).strip()] += 1

    if not candidates:
        return None
    # Return the most common photographer credit
    name, count = candidates.most_common(1)[0]
    # Only trust it if it appears in a meaningful portion of photos
    if count >= min(3, len(photos)):
        return name
    return None


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
            resp = self._call_api(
                self.api.photosets.getList,
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
        resp = self._call_api(
            self.api.photosets.getInfo,
            photoset_id=album_id,
            user_id=self.user_id,
        )
        return resp["photoset"]

    def get_album_photos(self, album_id: str) -> list[dict[str, Any]]:
        """Fetch all photos in an album with extras, handling pagination."""
        photos: list[dict[str, Any]] = []
        page = 1
        while True:
            resp = self._call_api(
                self.api.photosets.getPhotos,
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

    @staticmethod
    @_retry_api_call(max_retries=3, base_delay=1.0)
    def _call_api(api_method, **kwargs) -> dict[str, Any]:
        """Call a Flickr API method with retry logic."""
        return api_method(**kwargs)

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
