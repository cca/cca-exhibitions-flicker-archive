"""Tests for Flickr client utilities."""

import pytest

from cca_archive.flickr_client import extract_photographer_from_photos, parse_album_url, _parse_photo, _text
from cca_archive.models import PhotoRecord


def test_parse_album_url_standard():
    url = "https://www.flickr.com/photos/ccaexhibitions/albums/72177720312345678"
    assert parse_album_url(url) == "72177720312345678"


def test_parse_album_url_sets():
    url = "https://www.flickr.com/photos/ccaexhibitions/sets/72177720312345678/"
    assert parse_album_url(url) == "72177720312345678"


def test_parse_album_url_raw_id():
    assert parse_album_url("72177720312345678") == "72177720312345678"


def test_parse_album_url_invalid():
    with pytest.raises(ValueError):
        parse_album_url("https://example.com/not-a-flickr-url")


def test_text_extraction_dict():
    assert _text({"_content": "hello"}) == "hello"


def test_text_extraction_string():
    assert _text("hello") == "hello"


def test_text_extraction_none():
    assert _text(None) == ""


def test_parse_photo_minimal():
    data = {"id": "12345", "title": "Test", "views": "10"}
    photo = _parse_photo(data)
    assert photo.photo_id == "12345"
    assert photo.title == "Test"
    assert photo.views == 10


def test_parse_photo_with_description():
    data = {
        "id": "99",
        "title": "Art",
        "description": {"_content": "A nice photo"},
        "tags": "art gallery cca",
        "views": "0",
    }
    photo = _parse_photo(data)
    assert photo.description == "A nice photo"
    assert photo.tags == ["art", "gallery", "cca"]


def test_extract_photographer_from_titles():
    photos = [
        PhotoRecord(photo_id="1", title="Photo by Daniel Inclan Garcia"),
        PhotoRecord(photo_id="2", title="Photo by Daniel Inclan Garcia"),
        PhotoRecord(photo_id="3", title="Photo by Daniel Inclan Garcia"),
    ]
    assert extract_photographer_from_photos(photos) == "Daniel Inclan Garcia"


def test_extract_photographer_from_descriptions():
    photos = [
        PhotoRecord(photo_id="1", title="Afterlight", description="Photo by Hayley Lin"),
        PhotoRecord(photo_id="2", title="Afterlight", description="Photo by Hayley Lin"),
        PhotoRecord(photo_id="3", title="Afterlight", description="Photo by Hayley Lin"),
    ]
    assert extract_photographer_from_photos(photos) == "Hayley Lin"


def test_extract_photographer_none_when_no_credits():
    photos = [
        PhotoRecord(photo_id="1", title="IMG_001"),
        PhotoRecord(photo_id="2", title="IMG_002"),
    ]
    assert extract_photographer_from_photos(photos) is None


def test_extract_photographer_taken_by_variant():
    photos = [
        PhotoRecord(photo_id="1", title="Taken by Jane Doe"),
        PhotoRecord(photo_id="2", title="Taken by Jane Doe"),
        PhotoRecord(photo_id="3", title="Taken by Jane Doe"),
    ]
    assert extract_photographer_from_photos(photos) == "Jane Doe"
