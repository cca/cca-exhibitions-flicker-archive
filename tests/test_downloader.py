"""Tests for the async image downloader."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, call, patch

import httpx
import pytest

from cca_archive.downloader import _get_download_url, _get_extension, download_photos
from cca_archive.models import PhotoRecord


# ---------------------------------------------------------------------------
# _get_download_url
# ---------------------------------------------------------------------------


class TestGetDownloadUrl:
    def test_prefers_original(self):
        photo = PhotoRecord(
            photo_id="1",
            original_url="https://example.com/orig.jpg",
            large_url="https://example.com/large.jpg",
            medium_url="https://example.com/med.jpg",
        )
        assert _get_download_url(photo) == "https://example.com/orig.jpg"

    def test_falls_back_to_large(self):
        photo = PhotoRecord(
            photo_id="1",
            original_url=None,
            large_url="https://example.com/large.jpg",
            medium_url="https://example.com/med.jpg",
        )
        assert _get_download_url(photo) == "https://example.com/large.jpg"

    def test_falls_back_to_medium(self):
        photo = PhotoRecord(
            photo_id="1",
            original_url=None,
            large_url=None,
            medium_url="https://example.com/med.jpg",
        )
        assert _get_download_url(photo) == "https://example.com/med.jpg"

    def test_returns_none_when_no_urls(self):
        photo = PhotoRecord(photo_id="1")
        assert _get_download_url(photo) is None


# ---------------------------------------------------------------------------
# _get_extension
# ---------------------------------------------------------------------------


class TestGetExtension:
    def test_jpg(self):
        assert _get_extension("https://farm1.static.flickr.com/123/photo.jpg") == ".jpg"

    def test_png(self):
        assert _get_extension("https://example.com/image.png") == ".png"

    def test_gif(self):
        assert _get_extension("https://example.com/animated.gif") == ".gif"

    def test_url_with_query_params(self):
        assert _get_extension("https://example.com/photo.tiff?width=800") == ".tiff"

    def test_defaults_to_jpg_when_no_extension(self):
        assert _get_extension("https://example.com/photo") == ".jpg"

    def test_defaults_to_jpg_for_trailing_slash(self):
        assert _get_extension("https://example.com/photos/") == ".jpg"


# ---------------------------------------------------------------------------
# download_photos (async)
# ---------------------------------------------------------------------------


def _make_photo(photo_id: str, url: str | None = None) -> PhotoRecord:
    return PhotoRecord(photo_id=photo_id, original_url=url)


def _fake_response(content: bytes = b"fake-image-bytes", status_code: int = 200) -> httpx.Response:
    resp = httpx.Response(
        status_code=status_code,
        content=content,
        request=httpx.Request("GET", "https://example.com/img.jpg"),
    )
    return resp


@pytest.mark.asyncio
async def test_download_writes_file_and_sets_local_filename(tmp_path: Path):
    photo = _make_photo("42", "https://example.com/42.png")
    fake_resp = _fake_response(b"PNG image data")

    with patch("cca_archive.downloader.httpx.AsyncClient") as MockClient:
        mock_client = AsyncMock()
        mock_client.get.return_value = fake_resp
        MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await download_photos([photo], tmp_path)

    assert len(result) == 1
    assert result[0].local_filename == "42.png"
    saved = tmp_path / "42.png"
    assert saved.exists()
    assert saved.read_bytes() == b"PNG image data"


@pytest.mark.asyncio
async def test_skips_already_existing_files(tmp_path: Path):
    photo = _make_photo("99", "https://example.com/99.jpg")
    # Pre-create the file so it is treated as already downloaded.
    existing = tmp_path / "99.jpg"
    existing.write_bytes(b"already here")

    with patch("cca_archive.downloader.httpx.AsyncClient") as MockClient:
        mock_client = AsyncMock()
        MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await download_photos([photo], tmp_path)

    # HTTP get should never have been called.
    mock_client.get.assert_not_called()
    assert result[0].local_filename == "99.jpg"
    # Original file should be untouched.
    assert existing.read_bytes() == b"already here"


@pytest.mark.asyncio
async def test_handles_http_error_gracefully(tmp_path: Path):
    photo = _make_photo("77", "https://example.com/77.jpg")

    with patch("cca_archive.downloader.httpx.AsyncClient") as MockClient:
        mock_client = AsyncMock()
        mock_client.get.side_effect = httpx.HTTPStatusError(
            "Server Error",
            request=httpx.Request("GET", "https://example.com/77.jpg"),
            response=httpx.Response(500),
        )
        MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await download_photos([photo], tmp_path)

    assert len(result) == 1
    assert result[0].local_filename is None
    assert not (tmp_path / "77.jpg").exists()


@pytest.mark.asyncio
async def test_empty_photo_list(tmp_path: Path):
    with patch("cca_archive.downloader.httpx.AsyncClient") as MockClient:
        mock_client = AsyncMock()
        MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await download_photos([], tmp_path)

    assert result == []


# ---------------------------------------------------------------------------
# 429 retry behaviour
# ---------------------------------------------------------------------------


def _fake_429_response() -> httpx.Response:
    return httpx.Response(
        status_code=429,
        request=httpx.Request("GET", "https://example.com/img.jpg"),
    )


@pytest.mark.asyncio
async def test_retries_on_429_then_succeeds(tmp_path: Path):
    """First request returns 429, second succeeds — file should be downloaded."""
    photo = _make_photo("10", "https://example.com/10.jpg")
    resp_429 = _fake_429_response()
    resp_200 = _fake_response(b"image data")

    with (
        patch("cca_archive.downloader.httpx.AsyncClient") as MockClient,
        patch("cca_archive.downloader.asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
    ):
        mock_client = AsyncMock()
        # First call raises 429, second call succeeds
        mock_client.get.side_effect = [
            httpx.HTTPStatusError(
                "Too Many Requests",
                request=httpx.Request("GET", "https://example.com/10.jpg"),
                response=resp_429,
            ),
            resp_200,
        ]
        MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await download_photos([photo], tmp_path)

    assert result[0].local_filename == "10.jpg"
    assert (tmp_path / "10.jpg").read_bytes() == b"image data"
    # asyncio.sleep should have been called for the 429 backoff (4s on attempt 0)
    sleep_calls = [c for c in mock_sleep.call_args_list if c != call(0)]
    assert any(args[0] >= 4 for args, _ in [c for c in sleep_calls if c[0]])


@pytest.mark.asyncio
async def test_429_exhausts_retries(tmp_path: Path):
    """All attempts return 429 — download should fail after max attempts."""
    photo = _make_photo("11", "https://example.com/11.jpg")

    def _raise_429(*args, **kwargs):
        raise httpx.HTTPStatusError(
            "Too Many Requests",
            request=httpx.Request("GET", "https://example.com/11.jpg"),
            response=_fake_429_response(),
        )

    with (
        patch("cca_archive.downloader.httpx.AsyncClient") as MockClient,
        patch("cca_archive.downloader.asyncio.sleep", new_callable=AsyncMock),
    ):
        mock_client = AsyncMock()
        mock_client.get.side_effect = _raise_429
        MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await download_photos([photo], tmp_path)

    assert result[0].local_filename is None
    assert not (tmp_path / "11.jpg").exists()
    # Should have attempted 5 times (1 initial + 4 retries)
    assert mock_client.get.call_count == 5
