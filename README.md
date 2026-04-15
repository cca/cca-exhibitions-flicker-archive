# CCA Exhibitions Flickr Archive

Archives the CCA Exhibitions Flickr account (~15,000+ photos across 300+ albums). For each album the pipeline fetches Flickr metadata, extracts structured exhibition data from freeform descriptions via LLM, downloads images, optimizes them for web serving, converts them to pyramidal TIFFs for IIIF, and exports a flat CSV. A static Astro site renders the archive data.

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
| `DOWNLOAD_CONCURRENCY` | `3` | Simultaneous downloads / optimizations / TIFF conversions |
| `SKIP_LLM` | `false` | Disable LLM extraction globally |
| `SKIP_OPTIMIZE` | `false` | Disable image optimization globally |
| `IA_ACCESS_KEY` | — | Internet Archive API access key |
| `IA_SECRET_KEY` | — | Internet Archive API secret key |
| `IA_COLLECTION` | `opensource_image` | IA collection to upload into |
| `GCS_BUCKET` | — | Google Cloud Storage bucket name |
| `GCS_CREDENTIALS_FILE` | — | Path to GCS service account JSON (omit to use ADC) |
| `GCS_PUBLIC_BASE` | — | Public base URL for GCS bucket |

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
| `--skip-optimize` | Skip web image optimization (full + thumbnail JPEGs) |
| `--skip-tiff-convert` | Skip pyramidal TIFF conversion |
| `--skip-existing` | Skip albums already recorded as complete. Mutually exclusive with `--retry-llm-failures`. |
| `--retry-llm-failures` | Re-run LLM extraction and CSV export for albums where LLM previously failed. Skips downloads implicitly. |
| `--limit N` | Process at most N albums (useful with `--all`) |
| `--upload-ia` | Upload images to Internet Archive after processing |
| `--upload-gcs` | Upload web images and CSV to Google Cloud Storage after processing |

### Examples

```bash
# Metadata + CSV only, no image downloads or processing
uv run cca-archive --all --skip-download --skip-llm

# All albums, skip image processing (metadata + download + CSV only)
uv run cca-archive --all --skip-optimize --skip-tiff-convert

# Resume a previous run — skip albums already processed, cap at 10 new ones
uv run cca-archive --all --skip-existing --limit 10

# Full run with GCS upload
uv run cca-archive --all --upload-gcs
```

### Retry failed LLM extractions

```bash
uv run cca-archive --retry-llm-failures
```

### Convert TIFFs standalone

```bash
# Convert all downloaded JPEGs to pyramidal TIFFs (runs with 4 workers by default)
uv run cca-archive convert-tiffs
uv run cca-archive convert-tiffs --concurrency 8
```

### Sync existing output to cloud

```bash
uv run cca-archive sync --ia     # Internet Archive only
uv run cca-archive sync --gcs    # Google Cloud Storage only
uv run cca-archive sync          # both
```

### Backfill manifest from existing CSVs

```bash
uv run cca-archive backfill-manifest
```

## Pipeline stages

| Stage | Output | Skip flag |
|---|---|---|
| Flickr metadata fetch | in-memory | — |
| LLM extraction | `ExhibitionMetadata` struct | `--skip-llm` |
| Image download | `output/images/{slug}/` | `--skip-download` |
| Image optimization | `output/web/{slug}/` | `--skip-optimize` |
| TIFF conversion | `output/tiffs/{slug}/` | `--skip-tiff-convert` |
| CSV export | `output/csv/{slug}.csv` | — |
| Cloud upload | Internet Archive / GCS | _(opt-in)_ |

Every stage writes its status to `output/manifest.json`. Re-runs are safe — each stage skips work already done.

## Output

```
output/
├── images/{slug}/               # raw downloads (original resolution)
│   ├── 12345678.jpg
│   └── ...
├── web/{slug}/                  # optimized web JPEGs
│   ├── 12345678.jpg             # full size (≤2560px, ≤1MB)
│   └── 12345678_thumb.jpg       # thumbnail (≤400px)
├── tiffs/{slug}/                # pyramidal TIFFs for IIIF
│   └── 12345678.tif
├── csv/{slug}.csv               # one row per photo
└── manifest.json                # per-album, per-stage pipeline status
```

### CSV columns

Album-level fields are repeated on every row for flat export:

`album_id`, `album_title`, `album_url`, `album_photo_count`, `album_date_created`, `ia_identifier`, `exhibition_title`, `artists`, `curator`, `venue`, `address`, `photographer`, `opening_date`, `closing_date`, `reception_date`, `medium`, `description_summary`, `raw_description`, `photo_id`, `photo_title`, `photo_description`, `photo_tags`, `date_taken`, `date_uploaded`, `photo_views`, `license`, `original_url`, `local_filename`

Multi-value fields (artists, tags) are semicolon-separated.

## Frontend

An Astro static site in `frontend/` renders the archive data. It supports four image-serving backends (IIIF via Internet Archive or Cantaloupe, GCS-direct, or local optimized) selected by build-time env vars. See [`frontend/README.md`](frontend/README.md).

```bash
cd frontend && npm install && npm run dev   # local dev server at localhost:4321
```

## Deployment

Four deployment modes (bare local, Docker + Cantaloupe, Docker + nginx offline, GCS + Cloud Run) are documented in [`docs/deployment.md`](docs/deployment.md). Docker Compose files and Cloud Build configs are included in the repo.

## Validated example albums

| Album | ID | Photos | Era | What it tests |
|---|---|---|---|---|
| **Afterlight** | `72177720332161605` | 59 | 2026 | Structured modern format. Curator is a seminar, photographer backfilled from photo titles. |
| **Josh "Sioux" Reyes** | `72157691676973492` | 12 | 2018 | HTML tags, Instagram handle, "Images courtesy of" credit, stage-name ambiguity. |
| **New Look** | `72157659826175192` | 15 | 2015 | Sparse 114-char description; no artists, curator, or medium. |

```bash
uv run cca-archive 72177720332161605 --skip-download
uv run cca-archive 72157691676973492 --skip-download
uv run cca-archive 72157659826175192 --skip-download
```

## Development

```bash
uv run pytest                    # run all tests
uv run pytest tests/test_models.py::test_exhibition_metadata_full  # single test

# Research scripts
uv run python research/explore_api.py
uv run python research/explore_albums.py
uv run python research/explore_descriptions.py
```

## Swapping LLM providers

```bash
LLM_MODEL=anthropic:claude-sonnet-4-20250514
LLM_MODEL=openai:gpt-4o
```

## Documentation

- [`docs/pipeline-guide.md`](docs/pipeline-guide.md) — full module breakdown, CLI reference, env vars, manifest stage values
- [`docs/deployment.md`](docs/deployment.md) — Docker Compose modes, Cloud Build configs, GCS bucket layout
- [`frontend/README.md`](frontend/README.md) — frontend image serving modes, env vars, build commands

## Project structure

```
src/cca_archive/
├── config.py            # Settings from .env via pydantic-settings
├── models.py            # ExhibitionMetadata, PhotoRecord, AlbumRecord
├── flickr_client.py     # Flickr API wrapper (albums, photos, pagination)
├── llm.py               # pydantic-ai agent for metadata extraction
├── downloader.py        # Async image downloads with concurrency control
├── image_optimizer.py   # Resize JPEGs to web full + thumbnail (pyvips)
├── tiff_converter.py    # Convert JPEGs to pyramidal TIFFs (pyvips)
├── ia_uploader.py       # Internet Archive upload
├── gcs_uploader.py      # Google Cloud Storage upload
├── csv_export.py        # Flat CSV export (one row per photo)
├── manifest.py          # Per-album pipeline status manifest (CRUD)
└── pipeline.py          # CLI orchestrator
```
