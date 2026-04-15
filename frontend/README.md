# CCA Exhibitions Archive — Frontend

An Astro static site that renders the archive data produced by the Python pipeline. Supports multiple image-serving backends configured entirely through environment variables — no code changes needed to switch modes.

## Image serving modes

The frontend resolves image URLs at build time based on which env vars are set. Priority order:

| Mode | Env var to set | When to use |
|---|---|---|
| **Local optimized** | `PUBLIC_LOCAL_IMAGE_BASE=/web` | Offline/flash-drive exports; images bundled alongside the built site |
| **GCS-direct** | `PUBLIC_GCS_IMAGE_BASE_URL=https://storage.googleapis.com/bucket` | Frontend on GCS/CDN, images served directly from GCS web-optimized folder |
| **Internet Archive IIIF** | `PUBLIC_IIIF_BASE_URL=https://iiif.archive.org/image/iiif` | Images served via IA's IIIF server (requires ia_identifier in CSV data) |
| **Cantaloupe IIIF** | `PUBLIC_IIIF_BASE_URL=http://localhost:8182/iiif/3` | Local Docker dev or Cloud Run with a Cantaloupe sidecar |
| **Bare local dev** | _(none set)_ | No Docker, no IIIF — serves original downloaded files from `output/images/` |

Set at most one of `PUBLIC_LOCAL_IMAGE_BASE`, `PUBLIC_GCS_IMAGE_BASE_URL`, or `PUBLIC_IIIF_BASE_URL`. They are checked in priority order; the first match wins.

The GCS CSV loader (`PUBLIC_GCS_BASE_URL`) is independent — it controls where album CSV data is fetched from at build time and can be combined with any image mode.

## Environment variables

| Variable | Description |
|---|---|
| `PUBLIC_IIIF_BASE_URL` | IIIF Image API base URL (omit trailing slash) |
| `PUBLIC_GCS_BASE_URL` | GCS bucket base URL for fetching CSV data at build time |
| `PUBLIC_GCS_IMAGE_BASE_URL` | GCS base URL for pre-optimized web images (full + thumb JPEGs) |
| `PUBLIC_LOCAL_IMAGE_BASE` | Relative path prefix for locally bundled images (e.g. `/web`) |

## Commands

Run from the `frontend/` directory:

```bash
npm install          # install dependencies
npm run dev          # dev server at localhost:4321 (reads local output/csv/)
npm run build        # production build (reads env vars for image mode)
npm run build:offline  # build with LOCAL_IMAGE_BASE=/web (offline/flash-drive)
npm run preview      # preview production build locally
```

## Data loading

Album data is loaded from CSV files produced by the pipeline:

- **Local** (`output/csv/*.csv`) — default for `npm run dev` and builds without `PUBLIC_GCS_BASE_URL`
- **GCS** (`$PUBLIC_GCS_BASE_URL/csv/manifest.json` + per-slug CSVs) — used when `PUBLIC_GCS_BASE_URL` is set

All data-loading functions (`getAllAlbums`, `getAlbumBySlug`, etc.) are async and cached after the first call.

## Output structure expected

```
output/
├── csv/
│   ├── manifest.json          # {"slugs": ["slug-a", "slug-b", ...]}  (GCS mode only)
│   ├── slug-a.csv
│   └── slug-b.csv
├── images/                    # raw downloads (bare local dev only)
│   └── {slug}/{photo_id}.jpg
└── web/                       # optimized JPEGs (local optimized mode)
    └── {slug}/
        ├── {photo_id}.jpg     # full size (≤2560px, ≤1MB)
        └── {photo_id}_thumb.jpg
```
