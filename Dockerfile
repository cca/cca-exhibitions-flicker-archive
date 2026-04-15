# Stage 1: Python pipeline
FROM python:3.12-slim AS pipeline

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

RUN apt-get update && apt-get install -y --no-install-recommends libvips42 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY src/ src/

# Stage 2: Frontend build
FROM node:22-slim AS frontend-build

WORKDIR /app/frontend

COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci

COPY frontend/ .

ARG PUBLIC_IIIF_BASE_URL=""
ENV PUBLIC_IIIF_BASE_URL=$PUBLIC_IIIF_BASE_URL
ARG PUBLIC_GCS_BASE_URL=""
ENV PUBLIC_GCS_BASE_URL=$PUBLIC_GCS_BASE_URL
ARG PUBLIC_GCS_IMAGE_BASE_URL=""
ENV PUBLIC_GCS_IMAGE_BASE_URL=$PUBLIC_GCS_IMAGE_BASE_URL
ARG PUBLIC_LOCAL_IMAGE_BASE=""
ENV PUBLIC_LOCAL_IMAGE_BASE=$PUBLIC_LOCAL_IMAGE_BASE

RUN npm run build

# Stage 3: Serve static files
FROM nginx:alpine AS serve

COPY --from=frontend-build /app/frontend/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 8080
