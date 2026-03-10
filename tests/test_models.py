"""Tests for Pydantic models."""

from datetime import date, datetime

from cca_archive.models import AlbumRecord, ExhibitionMetadata, PhotoRecord


def test_exhibition_metadata_minimal():
    meta = ExhibitionMetadata(
        exhibition_title="Test Exhibition",
        raw_description="Some description",
    )
    assert meta.exhibition_title == "Test Exhibition"
    assert meta.artists == []
    assert meta.curator is None


def test_exhibition_metadata_full():
    meta = ExhibitionMetadata(
        exhibition_title="Big Show",
        artists=["Alice", "Bob"],
        curator="Carol",
        venue="Wattis Institute",
        opening_date=date(2024, 1, 15),
        closing_date=date(2024, 3, 30),
        reception_date=date(2024, 1, 15),
        medium="mixed media",
        description_summary="A group show.",
        raw_description="<p>Big Show featuring Alice and Bob...</p>",
    )
    assert len(meta.artists) == 2
    assert meta.venue == "Wattis Institute"


def test_photo_record_defaults():
    photo = PhotoRecord(photo_id="12345")
    assert photo.photo_id == "12345"
    assert photo.tags == []
    assert photo.views == 0
    assert photo.local_filename is None


def test_album_record_with_photos():
    album = AlbumRecord(
        album_id="999",
        album_url="https://flickr.com/photos/user/albums/999",
        title="Test Album",
        photo_count=2,
        photos=[
            PhotoRecord(photo_id="1", title="Photo 1"),
            PhotoRecord(photo_id="2", title="Photo 2"),
        ],
    )
    assert len(album.photos) == 2
    assert album.exhibition is None
