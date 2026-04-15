import fs from "node:fs";
import path from "node:path";
import Papa from "papaparse";

const IIIF_BASE = import.meta.env.PUBLIC_IIIF_BASE_URL || "";
const GCS_BASE = import.meta.env.PUBLIC_GCS_BASE_URL || "";
const GCS_IMAGE_BASE = import.meta.env.PUBLIC_GCS_IMAGE_BASE_URL || "";
const LOCAL_IMAGE_BASE = import.meta.env.PUBLIC_LOCAL_IMAGE_BASE || "";

export interface Photo {
  photo_id: string;
  photo_title: string;
  photo_description: string;
  photo_tags: string[];
  date_taken: string;
  date_uploaded: string;
  photo_views: number;
  license: string;
  original_url: string;
  local_filename: string;
  ia_identifier: string;
  image_src: string; // resolved: IIIF URL, local path, or Flickr URL
  thumbnail_src: string; // IIIF thumbnail for grid views
}

export interface Album {
  album_id: string;
  album_title: string;
  album_url: string;
  album_photo_count: number;
  album_date_created: string;
  slug: string;
  ia_identifier: string;
  exhibition_title: string;
  artists: string[];
  curator: string;
  venue: string;
  address: string;
  photographer: string;
  opening_date: string;
  closing_date: string;
  reception_date: string;
  medium: string;
  description_summary: string;
  raw_description: string;
  photos: Photo[];
  cover_image: string;
  cover_thumbnail: string;
}

interface CsvRow {
  [key: string]: string;
}

const PROJECT_ROOT = path.resolve(process.cwd(), "..");
const CSV_DIR = path.join(PROJECT_ROOT, "output/csv");
const IMAGES_DIR = path.join(PROJECT_ROOT, "output/images");

function splitSemicolon(value: string): string[] {
  if (!value) return [];
  return value
    .split(";")
    .map((s) => s.trim())
    .filter(Boolean);
}

/**
 * Build a IIIF Image API URL for a given photo.
 * IA uses $ separator (URL-encoded as %24), Cantaloupe uses / (%2F).
 */
function iiifUrl(identifier: string, photoId: string, width: number): string {
  if (IIIF_BASE.includes("archive.org")) {
    const filename = `${photoId}.jpg`;
    return `${IIIF_BASE}/${identifier}%24${filename}/full/${width},/0/default.jpg`;
  }
  // Cantaloupe: use pyramidal TIFFs for efficient resizing
  const filename = `${photoId}.tif`;
  return `${IIIF_BASE}/${identifier}%2F${filename}/full/${width},/0/default.jpg`;
}

function resolveImageSrc(
  slug: string,
  localFilename: string,
  originalUrl: string,
  photoId: string,
  iaIdentifier: string,
): string {
  // Local optimized / offline build: relative image paths
  if (LOCAL_IMAGE_BASE) {
    return `${LOCAL_IMAGE_BASE}/${slug}/${photoId}.jpg`;
  }
  // GCS-direct: optimized web JPEG, no IIIF server needed
  if (GCS_IMAGE_BASE) {
    return `${GCS_IMAGE_BASE}/web/${slug}/${photoId}.jpg`;
  }
  // Internet Archive IIIF — requires ia_identifier
  if (IIIF_BASE && IIIF_BASE.includes("archive.org") && iaIdentifier) {
    return iiifUrl(iaIdentifier, photoId, 1600);
  }
  // Cantaloupe (local Docker or GCS Cloud Run) — uses slug/filename as identifier
  if (IIIF_BASE) {
    return iiifUrl(slug, photoId, 1600);
  }
  // Bare local dev (no Docker, no IIIF): serve original downloaded file
  if (localFilename) {
    const localPath = path.join(IMAGES_DIR, slug, localFilename);
    if (fs.existsSync(localPath)) return `/images/${slug}/${localFilename}`;
  }
  return originalUrl || "";
}

function resolveThumbnailSrc(
  slug: string,
  localFilename: string,
  photoId: string,
  iaIdentifier: string,
): string {
  // Local optimized / offline build: relative thumbnail paths
  if (LOCAL_IMAGE_BASE) {
    return `${LOCAL_IMAGE_BASE}/${slug}/${photoId}_thumb.jpg`;
  }
  // GCS-direct: optimized thumbnail JPEG, no IIIF server needed
  if (GCS_IMAGE_BASE) {
    return `${GCS_IMAGE_BASE}/web/${slug}/${photoId}_thumb.jpg`;
  }
  // Internet Archive IIIF — requires ia_identifier
  if (IIIF_BASE && IIIF_BASE.includes("archive.org") && iaIdentifier) {
    return iiifUrl(iaIdentifier, photoId, 400);
  }
  // Cantaloupe (local Docker or GCS Cloud Run) — uses slug/filename as identifier
  if (IIIF_BASE) {
    return iiifUrl(slug, photoId, 400);
  }
  // Bare local dev: no thumbnails
  return "";
}

function parseAlbumCsvText(text: string, slug: string): Album {
  const result = Papa.parse<CsvRow>(text, {
    header: true,
    skipEmptyLines: true,
  });

  const rows = result.data;
  if (rows.length === 0) {
    throw new Error(`Empty CSV for slug: ${slug}`);
  }

  const first = rows[0];
  const iaIdentifier = first.ia_identifier || "";

  const photos: Photo[] = rows.map((row) => {
    const rowIaId = row.ia_identifier || iaIdentifier;
    const imageSrc = resolveImageSrc(slug, row.local_filename, row.original_url, row.photo_id, rowIaId);
    const thumbnailSrc = resolveThumbnailSrc(slug, row.local_filename, row.photo_id, rowIaId);
    return {
      photo_id: row.photo_id,
      photo_title: row.photo_title || "",
      photo_description: row.photo_description || "",
      photo_tags: splitSemicolon(row.photo_tags),
      date_taken: row.date_taken || "",
      date_uploaded: row.date_uploaded || "",
      photo_views: parseInt(row.photo_views, 10) || 0,
      license: row.license || "",
      original_url: row.original_url || "",
      local_filename: row.local_filename || "",
      ia_identifier: rowIaId,
      image_src: imageSrc,
      thumbnail_src: thumbnailSrc,
    };
  });

  const coverPhoto = photos.find((p) => p.image_src);
  const cover = coverPhoto?.image_src || "";
  const coverThumb = coverPhoto?.thumbnail_src || "";

  return {
    album_id: first.album_id,
    album_title: first.album_title,
    album_url: first.album_url,
    album_photo_count: parseInt(first.album_photo_count, 10) || 0,
    album_date_created: first.album_date_created || "",
    slug,
    ia_identifier: iaIdentifier,
    exhibition_title: first.exhibition_title || "",
    artists: splitSemicolon(first.artists),
    curator: first.curator || "",
    venue: first.venue || "",
    address: first.address || "",
    photographer: first.photographer || "",
    opening_date: first.opening_date || "",
    closing_date: first.closing_date || "",
    reception_date: first.reception_date || "",
    medium: first.medium || "",
    description_summary: first.description_summary || "",
    raw_description: first.raw_description || "",
    photos,
    cover_image: cover,
    cover_thumbnail: coverThumb,
  };
}

function parseAlbumCsv(filePath: string): Album {
  const content = fs.readFileSync(filePath, "utf-8");
  const slug = path.basename(filePath, ".csv");
  return parseAlbumCsvText(content, slug);
}

async function _loadFromGcs(): Promise<Album[]> {
  const res = await fetch(`${GCS_BASE}/csv/manifest.json`);
  if (!res.ok) return [];
  const manifest = await res.json() as { slugs: string[] };
  const albums = await Promise.all(
    manifest.slugs.map(async (slug) => {
      const r = await fetch(`${GCS_BASE}/csv/${slug}.csv`);
      if (!r.ok) return null;
      return parseAlbumCsvText(await r.text(), slug);
    })
  );
  return albums.filter((a): a is Album => a !== null);
}

function _loadFromFilesystem(): Album[] {
  if (!fs.existsSync(CSV_DIR)) return [];
  return fs.readdirSync(CSV_DIR)
    .filter((f) => f.endsWith(".csv"))
    .sort()
    .map((f) => parseAlbumCsv(path.join(CSV_DIR, f)));
}

let _cache: Promise<Album[]> | null = null;

export function getAllAlbums(): Promise<Album[]> {
  if (!_cache)
    _cache = GCS_BASE ? _loadFromGcs() : Promise.resolve(_loadFromFilesystem());
  return _cache;
}

export async function getAlbumBySlug(slug: string): Promise<Album | undefined> {
  const albums = await getAllAlbums();
  return albums.find((a) => a.slug === slug);
}

/** Group albums by academic year (Aug-Jul). Key format: "2023-24" */
export async function getAlbumsByYear(): Promise<Map<string, Album[]>> {
  const albums = await getAllAlbums();
  const map = new Map<string, Album[]>();
  for (const album of albums) {
    const date = album.opening_date || album.album_date_created;
    if (!date) continue;
    const d = new Date(date);
    const month = d.getMonth(); // 0-indexed
    const year = d.getFullYear();
    // Academic year: Aug (7) through Jul (6)
    const startYear = month >= 7 ? year : year - 1;
    const key = `${startYear}-${String(startYear + 1).slice(2)}`;
    if (!map.has(key)) map.set(key, []);
    map.get(key)!.push(album);
  }
  // Sort keys chronologically
  return new Map([...map.entries()].sort(([a], [b]) => a.localeCompare(b)));
}

/** Return a random album */
export async function getRandomAlbum(): Promise<Album | undefined> {
  const albums = await getAllAlbums();
  if (albums.length === 0) return undefined;
  return albums[Math.floor(Math.random() * albums.length)];
}

/** Return the N most recently created albums */
export async function getRecentAlbums(n: number): Promise<Album[]> {
  const albums = await getAllAlbums();
  return [...albums]
    .sort((a, b) => {
      const da = a.album_date_created || "";
      const db = b.album_date_created || "";
      return db.localeCompare(da);
    })
    .slice(0, n);
}
