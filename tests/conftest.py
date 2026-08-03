"""Shared pytest fixtures for Flickr client tests."""

import pytest

from cca_archive.models import PhotoRecord


@pytest.fixture
def sample_album_from_list():
    """Sample album dict from photosets.getList (get_all_albums)."""
    return {
        "id": "72177720332161605",
        "owner": "136995765@N03",
        "username": "ccaexhibitions",
        "primary": "55112025026",
        "secret": "bc6364c260",
        "server": "65535",
        "farm": 66,
        "count_views": "4",
        "count_comments": "0",
        "count_photos": 3,
        "count_videos": 0,
        "title": {"_content": "Test Exhibition"},
        "description": {
            "_content": "Jan 21–Feb 20, 2026\nNovack Gallery\n\nA test exhibition."
        },
        "can_comment": 0,
        "date_create": "1771861647",
        "date_update": "1771861775",
        "sorting_option_id": "manual-add-to-end",
        "photos": 3,
        "videos": 0,
        "visibility_can_see_set": 1,
        "needs_interstitial": 0,
    }


@pytest.fixture
def sample_album_from_info():
    """Sample album dict from photosets.getInfo (get_album_info).
    
    This should be identical to sample_album_from_list for testing
    that we can skip this redundant call.
    """
    return {
        "id": "72177720332161605",
        "owner": "136995765@N03",
        "username": "ccaexhibitions",
        "primary": "55112025026",
        "secret": "bc6364c260",
        "server": "65535",
        "farm": 66,
        "count_views": "4",
        "count_comments": "0",
        "count_photos": 3,
        "count_videos": 0,
        "title": {"_content": "Test Exhibition"},
        "description": {
            "_content": "Jan 21–Feb 20, 2026\nNovack Gallery\n\nA test exhibition."
        },
        "can_comment": 0,
        "date_create": "1771861647",
        "date_update": "1771861775",
        "sorting_option_id": "manual-add-to-end",
        "photos": 3,
        "visibility_can_see_set": 1,
        "needs_interstitial": 0,
    }


@pytest.fixture
def sample_photos_response():
    """Sample photos from photosets.getPhotos."""
    return [
        {
            "id": "55112025026",
            "title": "Installation view 1",
            "description": {"_content": "Gallery installation"},
            "tags": "art gallery exhibition",
            "datetaken": "2026-01-21 10:00:00",
            "dateupload": "1771861650",
            "views": "10",
            "license": "0",
            "url_o": "https://live.staticflickr.com/65535/55112025026_orig.jpg",
            "url_l": "https://live.staticflickr.com/65535/55112025026_large.jpg",
            "url_m": "https://live.staticflickr.com/65535/55112025026_medium.jpg",
        },
        {
            "id": "55112025027",
            "title": "Installation view 2",
            "description": {"_content": ""},
            "tags": "",
            "datetaken": "2026-01-21 10:05:00",
            "dateupload": "1771861655",
            "views": "8",
            "license": "4",
            "url_o": None,
            "url_l": "https://live.staticflickr.com/65535/55112025027_large.jpg",
            "url_m": "https://live.staticflickr.com/65535/55112025027_medium.jpg",
        },
        {
            "id": "55112025028",
            "title": "Installation view 3",
            "description": {"_content": "Detail shot"},
            "tags": "art",
            "datetaken": "2026-01-21 10:10:00",
            "dateupload": "1771861660",
            "views": "5",
            "license": "9",
            "url_o": "https://live.staticflickr.com/65535/55112025028_orig.jpg",
            "url_l": None,
            "url_m": "https://live.staticflickr.com/65535/55112025028_medium.jpg",
        },
    ]


@pytest.fixture
def sample_photo_records():
    """Pre-constructed PhotoRecord objects for testing."""
    return [
        PhotoRecord(
            photo_id="55112025026",
            title="Installation view 1",
            description="Gallery installation",
            tags=["art", "gallery", "exhibition"],
        ),
        PhotoRecord(
            photo_id="55112025027",
            title="Installation view 2",
        ),
        PhotoRecord(
            photo_id="55112025028",
            title="Installation view 3",
            description="Detail shot",
            tags=["art"],
        ),
    ]
