# Archive Pipeline — Technical Guide

A deep-dive into how the CCA Exhibitions Flickr archiver works: what each module does, why it's designed that way, and how all the pieces fit together.

---

## Data flow

```
Flickr API
    │
    ▼
FlickrClient          ← fetches albums, paginates photos, batches metadata
    │
    ▼
LLM extraction        ← pydantic-ai agent parses freeform descriptions
    │                         │
    ▼                         ▼
Downloader            Manifest (stage status written after each stage)
    │
    ▼
Image optimizer       ← resizes to web-ready full + thumbnail JPEGs (pyvips)
    │
    ▼
TIFF converter        ← pyramidal tiled TIFFs for IIIF serving (pyvips)
    │
    ▼
CSV export
    │
    ▼
Cloud upload          ← Internet Archive and/or Google Cloud Storage (optional)
```

All stages are orchestrated by `pipeline.py`. Each stage is independently skippable and idempotent — you can re-run the pipeline at any point without duplicating work.

---

## CLI reference

```
uv run cca-archive [album_url] [options]
uv run cca-archive sync [--ia] [--gcs]
```

### Main command

| Argument / Flag | Description |
|---|---|
| `album_url` | Flickr album URL (`…/albums/72177…`) or bare album ID |
| `--all` | Process all albums for the configured Flickr user |
| `--skip-download` | Skip image downloads; fetch metadata and export CSV only |
| `--skip-llm` | Skip LLM extraction; use raw Flickr data only |
| `--skip-optimize` | Skip web image optimization (full + thumbnail JPEG generation) |
| `--skip-tiff-convert` | Skip pyramidal TIFF conversion |
| `--skip-existing` | Skip albums recorded as complete in the manifest (`csv_export.status == "success"`), falling back to CSV file existence for pre-manifest albums. Mutually exclusive with `--retry-llm-failures`. |
| `--retry-llm-failures` | Re-run LLM extraction and CSV export for albums where `llm_extraction.status == "failed"` in the manifest. Downloads are skipped implicitly. Mutually exclusive with `--skip-existing`. |
| `--limit N` | Stop after processing N albums (applied after `--skip-existing`) |
| `--upload-ia` | Upload images to Internet Archive after each album |
| `--upload-gcs` | Upload web images and CSV to Google Cloud Storage after each album |

Album IDs can be extracted from any of these URL shapes:
- `https://www.flickr.com/photos/ccaexhibitions/albums/72177720332161605`
- `https://www.flickr.com/photos/ccaexhibitions/sets/72177720332161605`
- `72177720332161605` (bare ID)

### Sync subcommand

Use `sync` to upload already-downloaded local output to cloud storage without re-running the pipeline.

```bash
uv run cca-archive sync          # both IA and GCS
uv run cca-archive sync --ia     # Internet Archive only
uv run cca-archive sync --gcs    # Google Cloud Storage only
```

It scans `output/images/` for album directories and uploads each one.

### `convert-tiffs` subcommand

Standalone command to convert all downloaded JPEGs to pyramidal TIFFs without running the rest of the pipeline.

```bash
uv run cca-archive convert-tiffs
uv run cca-archive convert-tiffs --concurrency 8
```

Reads from `output/images/` and writes to `output/tiffs/`. Skips files that already have a corresponding TIFF.

### `backfill-manifest` subcommand

One-off command to populate `manifest.json` from existing CSVs. Useful when upgrading from a version before the manifest existed.

```bash
uv run cca-archive backfill-manifest
```

Reads every `output/csv/*.csv`, infers stage statuses from CSV contents, and writes them into the manifest. Skips albums that already have a manifest entry (idempotent). Inferred statuses:

| Stage | Inferred from CSV |
|---|---|
| `llm_extraction` | `success` if `exhibition_title` non-empty, else `unknown` |
| `image_download` | `success` if any `local_filename` non-empty, else `skipped` |
| `csv_export` | always `success` (file exists) |
| `ia_upload` | `success` if `ia_identifier` non-empty, else `not_attempted` |
| `gcs_upload` | always `not_attempted` (not inferrable from CSV) |

---

## Environment variables

All config lives in `.env` (loaded via pydantic-settings). Copy `.env.example` to get started.

### Flickr (required)

| Variable | Description |
|---|---|
| `FLICKR_API_KEY` | Flickr API key |
| `FLICKR_API_SECRET` | Flickr API secret |
| `FLICKR_USER_ID` | Flickr user ID for the target account |

### LLM

| Variable | Default | Description |
|---|---|---|
| `LLM_MODEL` | `anthropic:claude-sonnet-4-20250514` | pydantic-ai model string |
| `ANTHROPIC_API_KEY` | — | Required for Anthropic models |
| `OPENAI_API_KEY` | — | Required for OpenAI models |
| `SKIP_LLM` | `false` | Disable LLM extraction globally |

Switching providers is one env var change:

```bash
LLM_MODEL=anthropic:claude-sonnet-4-20250514
LLM_MODEL=openai:gpt-4o
```

### Processing

| Variable | Default | Description |
|---|---|---|
| `OUTPUT_DIR` | `output` | Root directory for all output |
| `DOWNLOAD_CONCURRENCY` | `3` | Simultaneous image downloads / optimizations / TIFF conversions |
| `SKIP_OPTIMIZE` | `false` | Disable image optimization globally |

### Internet Archive

| Variable | Default | Description |
|---|---|---|
| `IA_ACCESS_KEY` | — | IA API access key |
| `IA_SECRET_KEY` | — | IA API secret key |
| `IA_COLLECTION` | `opensource_image` | Collection to upload into |

### Google Cloud Storage

| Variable | Default | Description |
|---|---|---|
| `GCS_BUCKET` | — | GCS bucket name |
| `GCS_CREDENTIALS_FILE` | — | Path to service account JSON. Omit to use Application Default Credentials (ADC). |
| `GCS_PUBLIC_BASE` | — | Public base URL for the bucket (e.g. `https://storage.googleapis.com/my-bucket`). Used to construct public image URLs in the manifest. |

---

## Module breakdown

### `config.py` — Settings

A single `Settings` class (pydantic-settings) that loads all config from `.env`. Every other module receives a `Settings` instance rather than reading env vars directly — this makes testing straightforward and keeps config loading in one place.

Computed properties:
- `settings.images_dir` → `output_dir / "images"`
- `settings.web_dir` → `output_dir / "web"` (optimized JPEGs)
- `settings.tiffs_dir` → `output_dir / "tiffs"` (pyramidal TIFFs)
- `settings.csv_dir` → `output_dir / "csv"`
- `settings.manifest_path` → `output_dir / "manifest.json"`

---

### `manifest.py` — Pipeline status manifest

Tracks per-stage status for every album processed. Written to `output/manifest.json`, keyed by album slug.

**Key functions:**

| Function | Description |
|---|---|
| `load_manifest(settings)` | Read `manifest.json`; return `{}` if missing |
| `save_manifest(manifest, settings)` | Atomic write (`.tmp` → rename) |
| `update_stage(manifest, slug, album_id, title, stage, status, **kwargs)` | Upsert a stage entry with ISO timestamp; creates album entry if absent |
| `get_failed_llm_slugs(manifest)` | Returns slugs where `llm_extraction.status == "failed"` |

**Stage status values:**

| Stage | Valid statuses |
|---|---|
| `llm_extraction` | `success`, `failed`, `skipped` (no description or `--skip-llm`) |
| `image_download` | `success`, `partial` (some photos failed), `skipped` (`--skip-download`) |
| `image_optimization` | `success`, `partial`, `failed`, `skipped` (`--skip-optimize` or `--skip-download`) |
| `tiff_conversion` | `success`, `failed`, `skipped` (`--skip-tiff-convert` or `--skip-download`) |
| `csv_export` | `success`, `failed` |
| `ia_upload` | `not_attempted`, `success`, `failed` |
| `gcs_upload` | `not_attempted`, `success`, `failed` |

Albums with `image_download.status == "partial"` are not considered complete by `--skip-existing` and will be retried on the next run.

`pipeline.py` calls `update_stage` + `save_manifest` after each stage so the manifest reflects partial progress even if the pipeline is interrupted mid-album.

---

### `flickr_client.py` — Flickr API wrapper

**Batched extras**

The most important performance decision in the Flickr client: all photo metadata is fetched in a single `photosets.getPhotos` call using the `extras` parameter:

```
description, date_taken, date_upload, views, tags, license,
url_o, url_l, url_m, original_format
```

This avoids per-photo API calls entirely. Without batching, a 500-photo album would require 500+ API calls; with batching it's one (plus pagination).

**Pagination**

Both `get_all_albums()` and `get_album_photos()` use `per_page=500` and loop until `page == pages`. Flickr returns total page count in the first response.

**Retry logic**

All API calls are wrapped with `@_retry_api_call(max_retries=3, base_delay=1.0)`. Retries use exponential backoff (1s → 2s → 4s). Hard `FlickrAPIError` exceptions (like invalid API key) bypass retry and bubble up immediately.

**Text field parsing**

Flickr wraps text fields in `{"_content": "value"}`. A `_text()` helper normalizes this throughout the client so callers never see the raw nesting.

**Photographer backfill**

If the LLM doesn't extract a photographer, the client checks photo titles for patterns like:
- `Photo by Jane Smith`
- `Photos by Jane Smith`
- `Photographed by Jane Smith`
- `Taken by Jane Smith`
- `Images courtesy of Jane Smith`

It returns the most frequently occurring name if it appears in ≥3 photos or 100% of photos (whichever threshold is lower).

**License mapping**

Flickr returns a numeric license ID (0–10). The client maps these to human-readable strings:

| ID | License |
|---|---|
| 0 | All Rights Reserved |
| 1 | CC BY-NC-SA 2.0 |
| 2 | CC BY-NC 2.0 |
| 3 | CC BY-NC-ND 2.0 |
| 4 | CC BY 2.0 |
| 5 | CC BY-SA 2.0 |
| 6 | CC BY-ND 2.0 |
| 7 | No known copyright restrictions |
| 8 | US Government Work |
| 9 | CC0 1.0 |
| 10 | PDM 1.0 |

---

### `llm.py` — LLM metadata extraction

**What it does**

CCA Exhibitions album descriptions are freeform text — sometimes structured, sometimes sparse, sometimes full of HTML tags and typos. The LLM reads the raw description and returns a typed `ExhibitionMetadata` object.

One LLM call per album (not per photo). The call is async but albums are processed sequentially by default.

**Model**

Uses [pydantic-ai](https://ai.pydantic.dev/) with `output_type=ExhibitionMetadata`. The agent is initialized with the model string from `LLM_MODEL`. If using an Anthropic model with an explicit `ANTHROPIC_API_KEY`, the key is injected directly; otherwise pydantic-ai reads from environment variables.

**Prompt**

The system prompt (~165 lines) instructs the model to:
- Parse common CCA description formats (date range → venue → opening reception → credits → curator)
- Decode HTML entities (`&amp;` → `&`, `&quot;` → `"`)
- Strip HTML tags (`<a href="...">`, `<br>`, etc.)
- Recognize photographer credit patterns ("Photo by...", "Images courtesy of...")
- Distinguish venue name from street address (separate fields)
- List all artists uniquely, resolving stage name vs. legal name ambiguity
- Leave fields `null` rather than guessing

**Output schema**

```python
class ExhibitionMetadata(BaseModel):
    exhibition_title: str           # Required; defaults to album title if empty
    artists: list[str]              # All named artists
    curator: Optional[str]          # Curator name (not seminar/class names)
    venue: Optional[str]            # Gallery name only
    address: Optional[str]          # Street address, separate from venue
    photographer: Optional[str]     # Credit from description text
    opening_date: Optional[date]    # ISO date
    closing_date: Optional[date]
    reception_date: Optional[date]  # Opening reception date, if separate
    medium: Optional[str]           # Media/materials
    description_summary: Optional[str]  # 1–2 sentence summary
    raw_description: str            # Original description, always preserved
```

**Empty description handling**

If the album has no description (empty or whitespace), extraction is skipped and a minimal `ExhibitionMetadata` is returned with only `exhibition_title` set. This avoids a wasted LLM call.

---

### `downloader.py` — Async image downloader

**Concurrency**

Downloads run concurrently using `asyncio.Semaphore(concurrency)` (default: 3). Each photo acquires the semaphore before making an HTTP request. Adjust `DOWNLOAD_CONCURRENCY` in `.env` if you want to speed up or slow down fetching.

**URL fallback chain**

For each photo, the downloader tries URLs in priority order:
1. `url_o` — original resolution
2. `url_l` — large (1024px)
3. `url_m` — medium (500px)

If none are available, the photo is skipped and logged.

**Idempotency**

Before downloading, the downloader checks whether the file already exists and has a non-zero size. If so, it skips the download and returns the cached `PhotoRecord` with `local_filename` already set. This means re-running the pipeline after an interruption only fetches what's missing.

**Retry behavior**

Each photo gets up to 5 attempts (1 initial + 4 retries):
- `httpx.TimeoutException` → retry
- HTTP 429 → retry with shared backoff (see below)
- HTTP 5xx → retry
- HTTP 4xx (except 429) → fail immediately

**Shared 429 backoff**

Flickr's CDN rate-limits aggressively. When any download task receives a 429, a shared `backoff_until` timestamp is set and all concurrent tasks pause until it clears. Backoff intervals follow exponential progression: 4s → 8s → 16s → 32s. The `Retry-After` response header is respected if present.

This shared-backoff approach avoids the thundering herd problem where 3 concurrent tasks all retry simultaneously and immediately hit 429 again.

---

### `image_optimizer.py` — Web image optimization

Resizes downloaded JPEGs into two derivative formats for web serving:

| Derivative | Max dimension | Quality | Max file size |
|---|---|---|---|
| Full (`{photo_id}.jpg`) | 2560px on longest side | Q=85 (Q=75 fallback if >1MB) | 1MB |
| Thumbnail (`{photo_id}_thumb.jpg`) | 400px on longest side | Q=85 | — |

Uses [pyvips](https://libvips.github.io/pyvips/) for fast, memory-efficient resizing. Runs async using `asyncio.Semaphore` with `DOWNLOAD_CONCURRENCY` workers. Skips photos where both derivatives already exist.

Output goes to `output/web/{slug}/`.

**Key functions:**

| Function | Description |
|---|---|
| `optimize_album_images(slug, images_dir, web_dir, concurrency)` | Optimize all photos in one album |
| `optimize_all_images(images_dir, web_dir, concurrency)` | Optimize all albums (standalone use) |

Returns `(optimized_count, skipped_count, failed_photo_ids)`.

---

### `tiff_converter.py` — Pyramidal TIFF conversion

Converts downloaded JPEGs to pyramidal tiled TIFFs suitable for IIIF serving via Cantaloupe or Internet Archive:

- Tile size: 256×256px
- Compression: JPEG (Q=85)
- Pyramid levels: auto-generated by pyvips

Uses pyvips with sequential access (streaming, low memory). Runs async with semaphore concurrency. Skips photos where a TIFF already exists.

Output goes to `output/tiffs/{slug}/`.

**Key functions:**

| Function | Description |
|---|---|
| `convert_album_tiffs(slug, images_dir, tiffs_dir, concurrency)` | Convert all photos in one album |
| `convert_all_tiffs(images_dir, tiffs_dir, concurrency)` | Convert all albums (used by `convert-tiffs` subcommand) |

---

### `csv_export.py` — CSV export

**Format**

One row per photo. Album-level and exhibition-level fields are repeated on every row. This denormalized "flat" format makes the data immediately queryable in Excel, SQL, or pandas without any joins.

**Columns**

| Group | Columns |
|---|---|
| Album | `album_id`, `album_title`, `album_url`, `album_photo_count`, `album_date_created`, `slug`, `ia_identifier` |
| Exhibition (LLM) | `exhibition_title`, `artists`, `curator`, `venue`, `address`, `photographer`, `opening_date`, `closing_date`, `reception_date`, `medium`, `description_summary`, `raw_description` |
| Photo | `photo_id`, `photo_title`, `photo_description`, `photo_tags`, `date_taken`, `date_uploaded`, `photo_views`, `license`, `original_url`, `local_filename` |

**Multi-value fields**

`artists` and `photo_tags` are semicolon-separated within a single cell:

```
"Mei-Ling Chen; Aisha Okafor; Tomás Rivera"
```

**Filenames**

CSVs are named using the slugified album title: `{slugify(album.title)}.csv`. The same slug is used for the images directory, so the two always correspond.

---

### `models.py` — Data models

Three Pydantic models compose the data:

```
AlbumRecord
├── exhibition: ExhibitionMetadata   (from LLM)
└── photos: list[PhotoRecord]        (from Flickr API + downloader)
```

`AlbumRecord` is the primary unit of work. It's built up incrementally through the pipeline stages:
1. Created by `FlickrClient` with photos but no exhibition data
2. `exhibition` field populated by `llm.py`
3. `photos[n].local_filename` set by `downloader.py`
4. `ia_identifier` set by `ia_uploader.py` after upload
5. Passed to `csv_export.py` for final output

---

### `ia_uploader.py` — Internet Archive upload

**Identifier format**

Each album gets a deterministic IA identifier: `cca-exhibitions-{slugify(album.title)}`. Example: "Threads of Memory" → `cca-exhibitions-threads-of-memory`. This makes items findable and avoids duplicates on re-upload.

**Metadata**

The uploader enriches IA item metadata from the LLM extraction:

| IA field | Source |
|---|---|
| `title` | `exhibition_title` (or album title) |
| `creator` | `"CCA Exhibitions"` |
| `description` | `description_summary` or raw album description |
| `subject` | `artists` list |
| `contributor` | `curator` |
| `coverage` | `venue` |
| `date` | `opening_date` |

**Upload**

Uses the `internetarchive` Python library. Uploads all image files in `output/images/{slug}/`. The library is synchronous, so uploads run in an executor to avoid blocking the async event loop.

---

### `gcs_uploader.py` — Google Cloud Storage upload

**Authentication**

If `GCS_CREDENTIALS_FILE` is set, the uploader loads a service account JSON explicitly. If not, it falls back to Application Default Credentials (ADC) — the standard approach for running in GCP environments or with `gcloud auth application-default login` locally.

**Object paths**

| Local path | GCS object |
|---|---|
| `output/images/{slug}/{file}` | `images/{slug}/{file}` |
| `output/csv/{slug}.csv` | `csv/{slug}.csv` |

**File types**

Only recognized image formats are uploaded: `.jpg`, `.jpeg`, `.png`, `.gif`, `.tif`, `.tiff`, `.webp`.

---

## Output structure

```
output/
├── images/                          # raw downloads (original resolution)
│   ├── afterlight/
│   │   ├── 54321234.jpg
│   │   └── ...
│   └── josh-sioux-reyes/
│       └── ...
├── web/                             # optimized web JPEGs
│   └── afterlight/
│       ├── 54321234.jpg             # full size (≤2560px, ≤1MB)
│       └── 54321234_thumb.jpg       # thumbnail (≤400px)
├── tiffs/                           # pyramidal TIFFs for IIIF
│   └── afterlight/
│       └── 54321234.tif
├── csv/
│   ├── afterlight.csv
│   └── josh-sioux-reyes.csv
└── manifest.json
```

Image filenames use the Flickr photo ID. Album directory names and CSV filenames use the same slug so they always correspond.

---

## Idempotency and re-runs

The pipeline is safe to re-run at any point:

- **Flickr API calls**: always fetch fresh metadata (no local caching)
- **LLM extraction**: runs on every album unless `--skip-llm` is passed
- **Image downloads**: skip files that already exist with non-zero size
- **CSV export**: overwrites the existing CSV on each run
- **`--skip-existing`**: skips albums where `manifest.json` records `csv_export.status == "success"`, or where a CSV exists and there is no manifest entry (backward compat for pre-manifest runs). Fastest way to resume a large interrupted run.
- **`--retry-llm-failures`**: precisely targets albums where `llm_extraction.status == "failed"` in the manifest. Re-runs LLM + CSV only (downloads skipped implicitly). Use this after transient LLM errors (e.g. HTTP 529) instead of re-processing all albums.

Recommended pattern for resuming after an interruption:

```bash
uv run cca-archive --all --skip-existing --limit 20
```

This processes the next 20 unfinished albums and stops.

Recommended pattern for retrying LLM failures after a service outage:

```bash
uv run cca-archive --retry-llm-failures
```

---

## Research scripts

These scripts import from `cca_archive` and are meant for development exploration — testing the API, iterating on the LLM prompt, and surveying album formats before running the full pipeline.

```bash
# Dump raw Flickr API JSON responses to research/sample_output/
uv run python research/explore_api.py

# Print a summary table of all albums (ID, title, photo count, description length)
uv run python research/explore_albums.py

# Test LLM extraction on sample album descriptions and show structured output
uv run python research/explore_descriptions.py
```

---

## Validated test albums

These three albums exercise every edge case in the extraction pipeline:

| Album | ID | Photos | Era | What it tests |
|---|---|---|---|---|
| **Afterlight** | `72177720332161605` | 59 | 2026 | Modern structured format. Curator is a seminar (not a person), no named artists in description; photographer backfilled from photo titles. |
| **Josh "Sioux" Reyes** | `72157691676973492` | 12 | 2018 | HTML `<a>` tags, Instagram handles, quoted exhibition title, "Images courtesy of" credit pattern, stage-name ambiguity. |
| **New Look** | `72157659826175192` | 15 | 2015 | Sparse 114-character description. LLM must handle no artists, no curator, no medium. |

```bash
# Run all three (metadata + CSV, no image downloads)
uv run cca-archive 72177720332161605 --skip-download
uv run cca-archive 72157691676973492 --skip-download
uv run cca-archive 72157659826175192 --skip-download
```
