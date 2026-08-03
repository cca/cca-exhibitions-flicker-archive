"""Tests for Flickr client utilities."""

from unittest.mock import Mock, patch

import pytest

from cca_archive.flickr_client import (
    FlickrClient,
    extract_photographer_from_photos,
    parse_album_url,
    _parse_photo,
    _text,
)
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


# --- Integration tests for FlickrClient.build_album_record ---


@patch("cca_archive.flickr_client.FlickrClient.get_album_info")
@patch("cca_archive.flickr_client.FlickrClient.get_album_photos")
def test_build_album_record_without_album_data_calls_api(
    mock_get_photos, mock_get_info, sample_album_from_info, sample_photos_response
):
    """Test that build_album_record calls get_album_info when album_data is None."""
    from cca_archive.config import Settings

    # Mock the API responses
    mock_get_info.return_value = sample_album_from_info
    mock_get_photos.return_value = sample_photos_response

    # Create a mock settings object
    settings = Mock(spec=Settings)
    settings.flickr_api_key = "test_key"
    settings.flickr_api_secret = "test_secret"
    settings.flickr_user_id = "136995765@N03"

    client = FlickrClient(settings)
    album = client.build_album_record("72177720332161605", album_data=None)

    # Verify get_album_info was called (redundant call)
    mock_get_info.assert_called_once_with("72177720332161605")
    mock_get_photos.assert_called_once_with("72177720332161605")

    # Verify album record was built correctly
    assert album.album_id == "72177720332161605"
    assert album.title == "Test Exhibition"
    assert album.photo_count == 3
    assert len(album.photos) == 3


@patch("cca_archive.flickr_client.FlickrClient.get_album_info")
@patch("cca_archive.flickr_client.FlickrClient.get_album_photos")
def test_build_album_record_with_album_data_skips_api(
    mock_get_photos, mock_get_info, sample_album_from_list, sample_photos_response
):
    """Test that build_album_record skips get_album_info when album_data is provided."""
    from cca_archive.config import Settings

    # Mock only get_album_photos (get_album_info should NOT be called)
    mock_get_photos.return_value = sample_photos_response

    settings = Mock(spec=Settings)
    settings.flickr_api_key = "test_key"
    settings.flickr_api_secret = "test_secret"
    settings.flickr_user_id = "136995765@N03"

    client = FlickrClient(settings)
    album = client.build_album_record("72177720332161605", album_data=sample_album_from_list)

    # CRITICAL: Verify get_album_info was NOT called (optimization working!)
    mock_get_info.assert_not_called()
    # Verify get_album_photos was still called
    mock_get_photos.assert_called_once_with("72177720332161605")

    # Verify album record was built correctly from pre-fetched data
    assert album.album_id == "72177720332161605"
    assert album.title == "Test Exhibition"
    assert album.photo_count == 3
    assert len(album.photos) == 3


@patch("cca_archive.flickr_client.FlickrClient._call_api")
def test_build_album_record_produces_identical_results(
    mock_call_api, sample_album_from_list, sample_album_from_info, sample_photos_response
):
    """Test that both code paths produce identical AlbumRecord objects."""
    from cca_archive.config import Settings

    # Mock API responses: first call returns album info, second returns photos
    mock_call_api.side_effect = [
        {"photoset": sample_album_from_info},  # get_album_info response
        {"photoset": {"photo": sample_photos_response, "pages": 1}},  # get_album_photos response
        {"photoset": {"photo": sample_photos_response, "pages": 1}},  # get_album_photos second call
    ]

    settings = Mock(spec=Settings)
    settings.flickr_api_key = "test_key"
    settings.flickr_api_secret = "test_secret"
    settings.flickr_user_id = "136995765@N03"

    client = FlickrClient(settings)

    # Build album with API call (old way) - should call API twice (info + photos)
    album_with_api = client.build_album_record("72177720332161605", album_data=None)

    # Build album with pre-fetched data (optimized way) - should call API once (photos only)
    album_with_data = client.build_album_record("72177720332161605", album_data=sample_album_from_list)

    # Verify both produce identical results
    assert album_with_api.album_id == album_with_data.album_id
    assert album_with_api.title == album_with_data.title
    assert album_with_api.description == album_with_data.description
    assert album_with_api.photo_count == album_with_data.photo_count
    assert album_with_api.date_created == album_with_data.date_created
    assert album_with_api.date_updated == album_with_data.date_updated
    assert len(album_with_api.photos) == len(album_with_data.photos)

    # Verify API call counts: 2 calls for first build (info + photos), 1 call for second (photos only)
    assert mock_call_api.call_count == 3
