# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Project Does

Archives CCA Exhibitions' Flickr account (~15,000+ photos). For each album: fetches Flickr metadata, extracts structured exhibition data from freeform descriptions via LLM, downloads images, and exports flat CSV (one row per photo).

## Commands

```bash
# Install dependencies
uv sync

# Run all tests
uv run pytest

# Run a single test
uv run pytest tests/test_models.py::test_exhibition_metadata_full

# Run CLI
uv run cca-archive <album-url>
uv run cca-archive --all
uv run cca-archive --all --skip-download --skip-llm
uv run cca-archive --all --skip-optimize --skip-tiff-convert  # skip image processing
uv run cca-archive convert-tiffs                              # standalone TIFF conversion
uv run cca-archive sync --gcs                                 # upload existing output to GCS

# Run research scripts
uv run python research/explore_api.py
uv run python research/explore_albums.py
uv run python research/explore_descriptions.py
```

## Architecture

The pipeline flows linearly: **Flickr API → LLM extraction → image download → image optimization → TIFF conversion → CSV export → cloud upload**, orchestrated by `pipeline.py`.

- **config.py** — `Settings` class (pydantic-settings) loads everything from `.env`. All modules receive a `Settings` instance rather than reading env vars directly.
- **flickr_client.py** — Wraps `flickrapi.FlickrAPI` in JSON mode. Uses `extras` parameter on `getPhotos` to batch-fetch photo metadata (avoids per-photo API calls, respects 3,600 req/hr rate limit). Handles Flickr's `{"_content": "..."}` nesting pattern via `_text()` helper.
- **models.py** — Three Pydantic models: `ExhibitionMetadata` (LLM output type), `PhotoRecord`, `AlbumRecord`. The `AlbumRecord` composes the other two.
- **llm.py** — pydantic-ai `Agent` with `output_type=ExhibitionMetadata`. LLM provider is swappable via `LLM_MODEL` env var (e.g. `anthropic:claude-sonnet-4-20250514` → `openai:gpt-4o`). Returns structured data directly—no manual JSON parsing.
- **downloader.py** — Async httpx with semaphore concurrency. Falls back through URL sizes (original → large → medium). Skips existing files for idempotent re-runs.
- **image_optimizer.py** — Resizes downloaded JPEGs to web-ready full (≤2560px, ≤1MB) and thumbnail (≤400px) JPEGs using pyvips. Output goes to `output/web/`.
- **tiff_converter.py** — Converts JPEGs to pyramidal tiled TIFFs (256px tiles, JPEG compression) for IIIF serving via Cantaloupe or Internet Archive. Output goes to `output/tiffs/`.
- **ia_uploader.py** — Uploads album images to Internet Archive using the `internetarchive` library. Builds a deterministic item identifier (`cca-exhibitions-{slug}`) and enriches IA metadata from LLM extraction.
- **gcs_uploader.py** — Uploads web-optimized JPEGs, pyramidal TIFFs, and CSVs to Google Cloud Storage. Also writes a `csv/manifest.json` for the frontend to discover albums.
- **csv_export.py** — Flattens album+exhibition+photo into one row per photo. Multi-value fields (artists, tags) are semicolon-separated. Includes `ia_identifier` column.
- **pipeline.py** — CLI entry point via argparse. Calls the above modules in sequence. Async (`asyncio.run`). Subcommands: `sync`, `convert-tiffs`, `backfill-manifest`.

## Key Patterns

- Flickr API always returns JSON (configured in `FlickrClient.__init__`). Text fields are nested as `{"_content": "value"}`.
- The `research/` scripts import from `cca_archive` and are meant to be run during development to explore API data and iterate on the LLM extraction prompt/schema.
- Output goes to `output/` (gitignored): raw downloads in `output/images/`, optimized JPEGs in `output/web/`, pyramidal TIFFs in `output/tiffs/`, CSVs in `output/csv/`.
- Album slugs are generated via `python-slugify` and used for both folder names and CSV filenames.
- Image processing stages (optimization, TIFF conversion) reuse `DOWNLOAD_CONCURRENCY` for their semaphore limit. Skip them with `--skip-optimize` / `--skip-tiff-convert` when only metadata is needed.
- See `docs/pipeline-guide.md` for a full module breakdown and `docs/deployment.md` for Docker and Cloud Run deployment options.
