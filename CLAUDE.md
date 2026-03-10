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

# Run research scripts
uv run python research/explore_api.py
uv run python research/explore_albums.py
uv run python research/explore_descriptions.py
```

## Architecture

The pipeline flows linearly: **Flickr API → LLM extraction → image download → CSV export**, orchestrated by `pipeline.py`.

- **config.py** — `Settings` class (pydantic-settings) loads everything from `.env`. All modules receive a `Settings` instance rather than reading env vars directly.
- **flickr_client.py** — Wraps `flickrapi.FlickrAPI` in JSON mode. Uses `extras` parameter on `getPhotos` to batch-fetch photo metadata (avoids per-photo API calls, respects 3,600 req/hr rate limit). Handles Flickr's `{"_content": "..."}` nesting pattern via `_text()` helper.
- **models.py** — Three Pydantic models: `ExhibitionMetadata` (LLM output type), `PhotoRecord`, `AlbumRecord`. The `AlbumRecord` composes the other two.
- **llm.py** — pydantic-ai `Agent` with `output_type=ExhibitionMetadata`. LLM provider is swappable via `LLM_MODEL` env var (e.g. `anthropic:claude-sonnet-4-20250514` → `openai:gpt-4o`). Returns structured data directly—no manual JSON parsing.
- **downloader.py** — Async httpx with semaphore concurrency. Falls back through URL sizes (original → large → medium). Skips existing files for idempotent re-runs.
- **csv_export.py** — Flattens album+exhibition+photo into one row per photo. Multi-value fields (artists, tags) are semicolon-separated.
- **pipeline.py** — CLI entry point via argparse. Calls the above modules in sequence. Async (`asyncio.run`).

## Key Patterns

- Flickr API always returns JSON (configured in `FlickrClient.__init__`). Text fields are nested as `{"_content": "value"}`.
- The `research/` scripts import from `cca_archive` and are meant to be run during development to explore API data and iterate on the LLM extraction prompt/schema.
- Output goes to `output/` (gitignored). Images in `output/images/{album-slug}/`, CSVs in `output/csv/`.
- Album slugs are generated via `python-slugify` and used for both folder names and CSV filenames.
