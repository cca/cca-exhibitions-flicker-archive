"""Integration tests for image_optimizer.py using real downloaded images."""

import shutil
from pathlib import Path

import pytest
import pytest_asyncio

from cca_archive.image_optimizer import (
    optimize_album_images,
    optimize_image_full,
    optimize_image_thumb,
)

# Real images from output/images/ — skip tests gracefully if not present
LARGE_IMAGE = Path(
    "output/images/theo-lyons-archivist-desires-individualized-major/33654264178.jpg"
)
MEDIUM_IMAGE = Path(
    "output/images/theo-lyons-archivist-desires-individualized-major/46615516605.jpg"
)
SMALL_IMAGE = Path(
    "output/images/2018-commencement-exhibition/41756471005.jpg"
)

SAMPLE_IMAGES = [
    (LARGE_IMAGE, "32MB_large"),
    (MEDIUM_IMAGE, "25MB_medium"),
    (SMALL_IMAGE, "44KB_small"),
]


def _skip_if_missing(path: Path) -> pytest.MarkDecorator:
    return pytest.mark.skipif(
        not path.exists(),
        reason=f"Real image not present: {path}",
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("src_path,label", SAMPLE_IMAGES)
async def test_full_optimize_under_1mb(src_path: Path, label: str, tmp_path: Path) -> None:
    """Optimized full image must be <1MB."""
    if not src_path.exists():
        pytest.skip(f"Real image not present: {src_path}")
    out = tmp_path / f"{label}_full.jpg"
    await optimize_image_full(src_path, out)
    assert out.stat().st_size < 1_000_000, (
        f"Full image {label} is {out.stat().st_size} bytes, expected < 1MB"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("src_path,label", SAMPLE_IMAGES)
async def test_full_optimize_max_dimension(src_path: Path, label: str, tmp_path: Path) -> None:
    """Max side of optimized full image must be ≤ 2560px."""
    if not src_path.exists():
        pytest.skip(f"Real image not present: {src_path}")
    import pyvips

    out = tmp_path / f"{label}_full.jpg"
    await optimize_image_full(src_path, out)
    img = pyvips.Image.new_from_file(str(out))
    assert max(img.width, img.height) <= 2560


@pytest.mark.asyncio
@pytest.mark.parametrize("src_path,label", SAMPLE_IMAGES)
async def test_full_optimize_no_upscale(src_path: Path, label: str, tmp_path: Path) -> None:
    """Images already smaller than 2560px must not be upscaled."""
    if not src_path.exists():
        pytest.skip(f"Real image not present: {src_path}")
    import pyvips

    original = pyvips.Image.new_from_file(str(src_path))
    original_max = max(original.width, original.height)

    out = tmp_path / f"{label}_full.jpg"
    await optimize_image_full(src_path, out)
    result = pyvips.Image.new_from_file(str(out))
    assert max(result.width, result.height) <= original_max


@pytest.mark.asyncio
@pytest.mark.parametrize("src_path,label", SAMPLE_IMAGES)
async def test_thumbnail_max_dimension(src_path: Path, label: str, tmp_path: Path) -> None:
    """Thumbnail max side must be ≤ 400px."""
    if not src_path.exists():
        pytest.skip(f"Real image not present: {src_path}")
    import pyvips

    out = tmp_path / f"{label}_thumb.jpg"
    await optimize_image_thumb(src_path, out)
    img = pyvips.Image.new_from_file(str(out))
    assert max(img.width, img.height) <= 400


@pytest.mark.asyncio
async def test_skip_if_exists_full(tmp_path: Path) -> None:
    """optimize_image_full() must skip processing if destination already exists."""
    if not LARGE_IMAGE.exists():
        pytest.skip(f"Real image not present: {LARGE_IMAGE}")
    out = tmp_path / "existing_full.jpg"
    out.write_bytes(b"sentinel")
    mtime_before = out.stat().st_mtime
    await optimize_image_full(LARGE_IMAGE, out)
    assert out.stat().st_mtime == mtime_before, "File was modified when it should have been skipped"
    assert out.read_bytes() == b"sentinel", "File content changed when it should have been skipped"


@pytest.mark.asyncio
async def test_skip_if_exists_thumb(tmp_path: Path) -> None:
    """optimize_image_thumb() must skip processing if destination already exists."""
    if not LARGE_IMAGE.exists():
        pytest.skip(f"Real image not present: {LARGE_IMAGE}")
    out = tmp_path / "existing_thumb.jpg"
    out.write_bytes(b"sentinel")
    mtime_before = out.stat().st_mtime
    await optimize_image_thumb(LARGE_IMAGE, out)
    assert out.stat().st_mtime == mtime_before, "File was modified when it should have been skipped"


@pytest.mark.asyncio
async def test_album_optimize_creates_both_sizes(tmp_path: Path) -> None:
    """optimize_album_images() must create both full and _thumb variants in web_dir."""
    src_album = Path("output/images/theo-lyons-archivist-desires-individualized-major")
    if not src_album.exists():
        pytest.skip(f"Album directory not present: {src_album}")

    # Copy just two images into a temp images dir
    images_dir = tmp_path / "images"
    album_slug = "test-album"
    album_dir = images_dir / album_slug
    album_dir.mkdir(parents=True)

    photo_ids = []
    for jpg in sorted(src_album.glob("*.jpg"))[:2]:
        shutil.copy(jpg, album_dir / jpg.name)
        photo_ids.append(jpg.stem)

    web_dir = tmp_path / "web"
    await optimize_album_images(album_slug, images_dir, web_dir)

    for photo_id in photo_ids:
        assert (web_dir / album_slug / f"{photo_id}.jpg").exists(), (
            f"Missing full image for {photo_id}"
        )
        assert (web_dir / album_slug / f"{photo_id}_thumb.jpg").exists(), (
            f"Missing thumbnail for {photo_id}"
        )
