# CCA Exhibitions Flickr Archive

A Python tool for archiving CCA Exhibitions' Flickr account. Extracts structured exhibition metadata from album descriptions using an LLM, downloads images, and exports everything to CSV.

## Setup

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/).

```bash
# Install dependencies
uv sync

# Configure environment
cp .env.example .env
# Edit .env with your API keys
```

### Required environment variables

| Variable | Description |
|---|---|
| `FLICKR_API_KEY` | Flickr API key ([get one here](https://www.flickr.com/services/api/keys/)) |
| `FLICKR_API_SECRET` | Flickr API secret |
| `FLICKR_USER_ID` | Flickr user ID for the CCA Exhibitions account |
| `LLM_MODEL` | pydantic-ai model string (default: `anthropic:claude-sonnet-4-20250514`) |
| `ANTHROPIC_API_KEY` | Required if using an Anthropic model |
| `OPENAI_API_KEY` | Required if using an OpenAI model |

### Optional environment variables

| Variable | Default | Description |
|---|---|---|
| `OUTPUT_DIR` | `output` | Base directory for images and CSVs |
| `DOWNLOAD_CONCURRENCY` | `3` | Number of simultaneous image downloads |
| `SKIP_LLM` | `false` | Disable LLM extraction globally (same as `--skip-llm`) |
| `IA_ACCESS_KEY` | — | Internet Archive API access key |
| `IA_SECRET_KEY` | — | Internet Archive API secret key |
| `IA_COLLECTION` | `opensource_image` | IA collection to upload into |
| `GCS_BUCKET` | — | Google Cloud Storage bucket name |
| `GCS_CREDENTIALS_FILE` | — | Path to GCS service account JSON (omit to use ADC) |

## Usage

### Archive a single album

```bash
uv run cca-archive https://www.flickr.com/photos/ccaexhibitions/albums/72177720312345678
```

### Archive all albums

```bash
uv run cca-archive --all
```

### Options

| Flag | Description |
|---|---|
| `--all` | Process all albums for the configured user |
| `--skip-download` | Skip image downloads (metadata and CSV only) |
| `--skip-llm` | Skip LLM metadata extraction |
| `--skip-existing` | Skip albums already recorded as complete in the manifest (or with a CSV for pre-manifest albums). Mutually exclusive with `--retry-llm-failures`. |
| `--retry-llm-failures` | Re-run LLM extraction and CSV export for albums where LLM previously failed. Skips downloads implicitly. Mutually exclusive with `--skip-existing`. |
| `--limit N` | Process at most N albums (useful with `--all`) |
| `--upload-ia` | Upload images to Internet Archive after processing |
| `--upload-gcs` | Upload images and CSV to Google Cloud Storage after processing |

### Examples

```bash
# Metadata + CSV only, no image downloads
uv run cca-archive --skip-download https://www.flickr.com/photos/ccaexhibitions/albums/72177720312345678

# All albums, skip LLM (just raw Flickr data)
uv run cca-archive --all --skip-llm

# All albums, CSV only (fastest)
uv run cca-archive --all --skip-download --skip-llm

# Resume a previous run — skip albums already processed, cap at 10 new ones
uv run cca-archive --all --skip-existing --limit 10
```

### Retry failed LLM extractions

If LLM extraction failed transiently (e.g. HTTP 529 Overloaded), the manifest records which albums need a retry:

```bash
# Re-run LLM + CSV for all albums where extraction failed
uv run cca-archive --retry-llm-failures
```

### Backfill manifest from existing CSVs

If you have CSVs from before the manifest was introduced, populate the manifest in one shot:

```bash
uv run cca-archive backfill-manifest
```

This is idempotent — albums already in the manifest are skipped.

### Sync existing output to cloud

If you've already downloaded images locally and want to upload them without re-running the pipeline:

```bash
# Upload all local albums to Internet Archive
uv run cca-archive sync --ia

# Upload all local albums to Google Cloud Storage
uv run cca-archive sync --gcs

# Upload to both
uv run cca-archive sync
```

## Validated example albums

These 3 albums span the full range of description formats across 2015–2026 and exercise every extraction edge case in the pipeline.

| Album | ID | Photos | Era | What it tests |
|---|---|---|---|---|
| **Afterlight** | `72177720332161605` | 59 | 2026 | Structured modern format. Curator is a seminar (not a person), no named artists in description, photographer backfilled from photo titles. |
| **Josh "Sioux" Reyes** | `72157691676973492` | 12 | 2018 | HTML `<a>` tags in description, Instagram handle, quoted exhibition title, "Images courtesy of" credit pattern, artist stage-name ambiguity. |
| **New Look** | `72157659826175192` | 15 | 2015 | Sparse single-sentence description (114 chars). LLM must parse unstructured text with no artists, no curator, no medium. |

```bash
# Run all 3 (metadata + CSV only)
uv run cca-archive 72177720332161605 --skip-download
uv run cca-archive 72157691676973492 --skip-download
uv run cca-archive 72157659826175192 --skip-download
```

## Output

```
output/
├── images/{album-slug}/     # Downloaded photos
│   ├── 12345678.jpg
│   └── ...
├── csv/{album-slug}.csv     # One row per photo
└── manifest.json            # Per-album, per-stage pipeline status
```

### CSV columns

Album-level fields are repeated on every row for flat export:

`album_id`, `album_title`, `album_url`, `album_photo_count`, `album_date_created`, `ia_identifier`, `exhibition_title`, `artists`, `curator`, `venue`, `address`, `photographer`, `opening_date`, `closing_date`, `reception_date`, `medium`, `description_summary`, `raw_description`, `photo_id`, `photo_title`, `photo_description`, `photo_tags`, `date_taken`, `date_uploaded`, `photo_views`, `license`, `original_url`, `local_filename`

Multi-value fields (artists, tags) are semicolon-separated.

## Research scripts

These are for exploring the Flickr API and iterating on the LLM extraction schema:

```bash
# Dump raw API responses to research/sample_output/
uv run python research/explore_api.py

# Survey all albums with a summary table
uv run python research/explore_albums.py

# Test LLM extraction on sample descriptions
uv run python research/explore_descriptions.py
```

## Swapping LLM providers

Change the `LLM_MODEL` variable in `.env`:

```bash
# Anthropic
LLM_MODEL=anthropic:claude-sonnet-4-20250514

# OpenAI
LLM_MODEL=openai:gpt-4o
```

## Tests

```bash
uv run pytest
```

## Project structure

```
src/cca_archive/
├── config.py          # Settings from .env via pydantic-settings
├── models.py          # ExhibitionMetadata, PhotoRecord, AlbumRecord
├── flickr_client.py   # Flickr API wrapper (albums, photos, pagination)
├── llm.py             # pydantic-ai agent for metadata extraction
├── downloader.py      # Async image downloads with concurrency control
├── csv_export.py      # Flat CSV export (one row per photo)
├── manifest.py        # Per-album pipeline status manifest (CRUD)
└── pipeline.py        # CLI orchestrator
```
