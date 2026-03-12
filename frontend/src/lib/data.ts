import fs from "node:fs";
import path from "node:path";
import Papa from "papaparse";

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
  image_src: string; // resolved: local path or Flickr URL
  thumbnail_src: string; // WebP thumbnail for grid views
}

export interface Album {
  album_id: string;
  album_title: string;
  album_url: string;
  album_photo_count: number;
  album_date_created: string;
  slug: string;
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

function resolveImageSrc(slug: string, localFilename: string, originalUrl: string, photoId?: string): string {
  const id = localFilename ? path.parse(localFilename).name : photoId;

  // Prefer the processed 1600px WebP
  if (id) {
    const fullPath = path.join(IMAGES_DIR, slug, "full", `${id}.webp`);
    if (fs.existsSync(fullPath)) {
      return `/images/${slug}/full/${id}.webp`;
    }
  }

  // Fall back to original local file
  if (localFilename) {
    const localPath = path.join(IMAGES_DIR, slug, localFilename);
    if (fs.existsSync(localPath)) {
      return `/images/${slug}/${localFilename}`;
    }
  }
  if (!localFilename && photoId) {
    const fallback = `${photoId}.jpg`;
    const fallbackPath = path.join(IMAGES_DIR, slug, fallback);
    if (fs.existsSync(fallbackPath)) {
      return `/images/${slug}/${fallback}`;
    }
  }
  return originalUrl || "";
}

function resolveThumbnailSrc(slug: string, localFilename: string, photoId?: string): string {
  const id = localFilename ? path.parse(localFilename).name : photoId;
  if (!id) return "";
  const thumbPath = path.join(IMAGES_DIR, slug, "thumbs", `${id}.webp`);
  if (fs.existsSync(thumbPath)) {
    return `/images/${slug}/thumbs/${id}.webp`;
  }
  return "";
}

function parseAlbumCsv(filePath: string): Album {
  const content = fs.readFileSync(filePath, "utf-8");
  const result = Papa.parse<CsvRow>(content, {
    header: true,
    skipEmptyLines: true,
  });

  const rows = result.data;
  if (rows.length === 0) {
    throw new Error(`Empty CSV: ${filePath}`);
  }

  const first = rows[0];
  const slug = path.basename(filePath, ".csv");

  const photos: Photo[] = rows.map((row) => {
    const imageSrc = resolveImageSrc(slug, row.local_filename, row.original_url, row.photo_id);
    const thumbnailSrc = resolveThumbnailSrc(slug, row.local_filename, row.photo_id);
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

let _cache: Album[] | null = null;

export function getAllAlbums(): Album[] {
  if (_cache) return _cache;

  if (!fs.existsSync(CSV_DIR)) {
    return [];
  }

  const files = fs
    .readdirSync(CSV_DIR)
    .filter((f) => f.endsWith(".csv"))
    .sort();

  _cache = files.map((f) => parseAlbumCsv(path.join(CSV_DIR, f)));
  return _cache;
}

export function getAlbumBySlug(slug: string): Album | undefined {
  return getAllAlbums().find((a) => a.slug === slug);
}
