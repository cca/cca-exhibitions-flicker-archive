"""Pydantic models for Flickr archive data."""

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel


class ExhibitionMetadata(BaseModel):
    """LLM-extracted structured data from album description."""

    exhibition_title: str
    artists: list[str] = []
    curator: Optional[str] = None
    venue: Optional[str] = None
    opening_date: Optional[date] = None
    closing_date: Optional[date] = None
    reception_date: Optional[date] = None
    medium: Optional[str] = None
    description_summary: Optional[str] = None
    raw_description: str


class PhotoRecord(BaseModel):
    """A single photo from a Flickr album."""

    photo_id: str
    title: Optional[str] = None
    description: Optional[str] = None
    tags: list[str] = []
    date_taken: Optional[datetime] = None
    date_uploaded: Optional[datetime] = None
    views: int = 0
    license: Optional[str] = None
    original_url: Optional[str] = None
    large_url: Optional[str] = None
    medium_url: Optional[str] = None
    local_filename: Optional[str] = None


class AlbumRecord(BaseModel):
    """A Flickr album with exhibition metadata and photos."""

    album_id: str
    album_url: str
    title: str
    description: Optional[str] = None
    photo_count: int = 0
    date_created: Optional[datetime] = None
    date_updated: Optional[datetime] = None
    exhibition: Optional[ExhibitionMetadata] = None
    photos: list[PhotoRecord] = []
