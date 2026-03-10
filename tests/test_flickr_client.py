"""Tests for Flickr client utilities."""

import pytest

from cca_archive.flickr_client import parse_album_url, _parse_photo, _text


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
