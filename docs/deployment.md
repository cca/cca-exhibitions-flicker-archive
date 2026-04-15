# Deployment Guide

The archive can be deployed in several configurations depending on where images are served from and whether a IIIF server is needed. All modes use the same `Dockerfile` and `frontend/` codebase — the image-serving mode is selected by build-time env vars.

---

## Deployment modes

### 1. Bare local dev (no Docker)

No image server required. The frontend reads local CSVs and serves raw downloaded files via Astro's dev server.

```bash
# In repo root
uv run cca-archive --all                 # run pipeline
cd frontend && npm run dev               # start dev server at localhost:4321
```

Images are served from `output/images/{slug}/` at `/images/{slug}/...`. No env vars needed.

---

### 2. Local dev with Cantaloupe IIIF (Docker)

Uses `docker-compose.local-cantaloupe.yml`. Runs the pipeline, a Cantaloupe IIIF server backed by local pyramidal TIFFs, and the Astro dev server.

```bash
docker compose -f docker-compose.local-cantaloupe.yml up
```

Services:
- **iiif** — Cantaloupe 5.0.7 on `:8182`, serving TIFFs from `output/tiffs/`
- **pipeline** — runs `cca-archive --all --skip-download` (assumes images already downloaded)
- **frontend** — Astro dev server on `:4321` with `PUBLIC_IIIF_BASE_URL=http://localhost:8182/iiif/3`

Pipeline produces pyramidal TIFFs in `output/tiffs/`. Cantaloupe reads directly from that directory. Useful for testing IIIF zoom behavior locally.

---

### 3. Local optimized (offline / flash-drive export)

Uses `docker-compose.local-optimized.yml`. Runs the full pipeline, builds the static site, and serves it via nginx with web-optimized images bundled alongside.

```bash
docker compose -f docker-compose.local-optimized.yml up
```

Services:
- **pipeline** — runs `cca-archive --all`, producing `output/web/` (optimized JPEGs)
- **frontend** — builds the Astro site with `PUBLIC_LOCAL_IMAGE_BASE=/web`
- **web** — nginx on `:8080` serving the built site; mounts `output/web/` at `/web`

The result is a self-contained static site + image folder that works without any network access. Suitable for archival flash-drive exports or air-gapped installs.

---

### 4. GCS-direct (production, no IIIF server)

Uses `docker-compose.gcs-direct.yml`. The pipeline uploads web-optimized JPEGs to GCS; the frontend fetches CSVs from GCS at build time and points image URLs directly at GCS.

```bash
docker compose -f docker-compose.gcs-direct.yml up
```

Services:
- **pipeline** — runs `cca-archive --all`, uploading to GCS
- **frontend** — builds with `PUBLIC_GCS_BASE_URL` and `PUBLIC_GCS_IMAGE_BASE_URL` set

Required `.env` vars:
```
GCS_BUCKET=your-bucket
PUBLIC_GCS_BASE_URL=https://storage.googleapis.com/your-bucket
PUBLIC_GCS_IMAGE_BASE_URL=https://storage.googleapis.com/your-bucket
```

No IIIF server needed — images are served at fixed URLs (`/web/{slug}/{photo_id}.jpg`). Lower infrastructure cost than running Cantaloupe, at the cost of no deep-zoom capability.

---

## Cloud Run (GCP production)

Two frontend variants and one pipeline job are deployable to Cloud Run via Cloud Build.

### Pipeline job — `cloudbuild/update-pipeline-job.yaml`

Builds the `pipeline` Docker stage and deploys it as a Cloud Run Job. The job is configured to run `--all --skip-existing --upload-gcs` on demand or on a schedule.

Required substitutions (set in Cloud Build trigger config):
- _(none required beyond defaults)_

Secrets: the pipeline reads `.env` from Secret Manager (`cca-exhibitions-archive-settings:latest`). Mount path is `/app/.env`.

```bash
gcloud builds submit --config cloudbuild/update-pipeline-job.yaml .
```

---

### Frontend with Cantaloupe IIIF — `cloudbuild/deploy-frontend-cantaloupe.yaml`

Builds the `serve` Docker stage with `PUBLIC_GCS_BASE_URL` (CSVs from GCS) and `PUBLIC_IIIF_BASE_URL` (Cantaloupe Cloud Run service URL). Deploys as a Cloud Run Service.

Required substitutions:
- `_PUBLIC_GCS_BASE_URL` — e.g. `https://storage.googleapis.com/your-bucket`
- `_PUBLIC_IIIF_BASE_URL` — Cantaloupe Cloud Run service URL

Also deploy the Cantaloupe service (see below).

```bash
gcloud builds submit --config cloudbuild/deploy-frontend-cantaloupe.yaml \
  --substitutions=_PUBLIC_GCS_BASE_URL=...,_PUBLIC_IIIF_BASE_URL=... .
```

---

### Frontend GCS-direct — `cloudbuild/deploy-frontend-gcs-direct.yaml`

Builds the `serve` stage with `PUBLIC_GCS_BASE_URL` and `PUBLIC_GCS_IMAGE_BASE_URL`. No IIIF server dependency.

Required substitutions:
- `_PUBLIC_GCS_BASE_URL` — CSV manifest base URL
- `_PUBLIC_GCS_IMAGE_BASE_URL` — web image base URL

```bash
gcloud builds submit --config cloudbuild/deploy-frontend-gcs-direct.yaml \
  --substitutions=_PUBLIC_GCS_BASE_URL=...,_PUBLIC_GCS_IMAGE_BASE_URL=... .
```

---

### Cantaloupe IIIF service — `cloudbuild/deploy-cantaloupe.yaml`

Deploys a Cantaloupe 5.0.7 container as a Cloud Run Service. Configured to use `HttpSource` pointing at the GCS `tiffs/` prefix — no persistent volume needed.

Required substitutions:
- `_GCS_BUCKET` — GCS bucket name (Cantaloupe will fetch TIFFs from `https://storage.googleapis.com/{bucket}/tiffs/`)

```bash
gcloud builds submit --config cloudbuild/deploy-cantaloupe.yaml \
  --substitutions=_GCS_BUCKET=your-bucket .
```

Default: 1 CPU, 1 GiB RAM, 0–4 instances. TIFFs must be publicly readable or the service account must have Storage Object Viewer.

---

## Docker image stages

The `Dockerfile` has three named stages:

| Stage | Contents | Used by |
|---|---|---|
| `pipeline` | Python 3.12-slim + uv + libvips + cca_archive package | Pipeline job, local compose |
| `frontend-build` | Node 22 + Astro build output | Intermediate (not deployed directly) |
| `serve` | nginx:alpine + built static site | Frontend Cloud Run service, local compose `web` |

Build args accepted by `frontend-build` / `serve`:

| Arg | Description |
|---|---|
| `PUBLIC_IIIF_BASE_URL` | IIIF Image API base URL |
| `PUBLIC_GCS_BASE_URL` | GCS base URL for CSV data |
| `PUBLIC_GCS_IMAGE_BASE_URL` | GCS base URL for web images |
| `PUBLIC_LOCAL_IMAGE_BASE` | Relative path for locally bundled images |

---

## GCS bucket layout

The pipeline writes to and the frontend reads from this bucket structure:

```
gs://your-bucket/
├── csv/
│   ├── manifest.json          # {"slugs": ["slug-a", ...]}
│   └── {slug}.csv
├── web/
│   └── {slug}/
│       ├── {photo_id}.jpg     # full-size optimized JPEG (≤2560px)
│       └── {photo_id}_thumb.jpg
└── tiffs/
    └── {slug}/
        └── {photo_id}.tif     # pyramidal tiled TIFF for Cantaloupe
```
