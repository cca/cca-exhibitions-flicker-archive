import fs from "node:fs";
import path from "node:path";
import sharp from "sharp";
import pLimit from "p-limit";

const PROJECT_ROOT = path.resolve(import.meta.dirname, "../..");
const IMAGES_DIR = path.join(PROJECT_ROOT, "output/images");
const PUBLIC_IMAGES = path.join(import.meta.dirname, "../public/images");

const THUMB_WIDTH = 400;
const FULL_WIDTH = 1600;
const WEBP_QUALITY = 75;
const CONCURRENCY = 8;

interface Stats {
  thumbGenerated: number;
  thumbSkipped: number;
  fullGenerated: number;
  fullSkipped: number;
}

async function processImages(): Promise<Stats> {
  const slugDirs = fs
    .readdirSync(IMAGES_DIR, { withFileTypes: true })
    .filter((d) => d.isDirectory() && d.name !== "thumbs" && d.name !== "full");

  const limit = pLimit(CONCURRENCY);
  const tasks: Promise<void>[] = [];
  const stats: Stats = {
    thumbGenerated: 0,
    thumbSkipped: 0,
    fullGenerated: 0,
    fullSkipped: 0,
  };

  for (const dir of slugDirs) {
    const slugPath = path.join(IMAGES_DIR, dir.name);
    const thumbsDir = path.join(slugPath, "thumbs");
    const fullDir = path.join(slugPath, "full");

    const files = fs
      .readdirSync(slugPath)
      .filter((f) => /\.(jpe?g|png)$/i.test(f));

    if (files.length === 0) continue;

    for (const file of files) {
      const id = path.parse(file).name;
      const srcPath = path.join(slugPath, file);

      // Thumbnail (400px)
      const thumbDest = path.join(thumbsDir, `${id}.webp`);
      if (fs.existsSync(thumbDest)) {
        stats.thumbSkipped++;
      } else {
        tasks.push(
          limit(async () => {
            fs.mkdirSync(thumbsDir, { recursive: true });
            await sharp(srcPath)
              .resize({ width: THUMB_WIDTH })
              .webp({ quality: WEBP_QUALITY })
              .toFile(thumbDest);
            stats.thumbGenerated++;
          })
        );
      }

      // Full-size (1600px)
      const fullDest = path.join(fullDir, `${id}.webp`);
      if (fs.existsSync(fullDest)) {
        stats.fullSkipped++;
      } else {
        tasks.push(
          limit(async () => {
            fs.mkdirSync(fullDir, { recursive: true });
            await sharp(srcPath)
              .resize({ width: FULL_WIDTH, withoutEnlargement: true })
              .webp({ quality: WEBP_QUALITY })
              .toFile(fullDest);
            stats.fullGenerated++;
          })
        );
      }
    }
  }

  await Promise.all(tasks);
  return stats;
}

/**
 * Set up public/images so only the processed WebP directories (thumbs/ and
 * full/) are visible to the Astro build — originals are excluded from dist.
 */
function linkPublicImages(): void {
  // Remove old symlink if it points directly at output/images
  if (fs.existsSync(PUBLIC_IMAGES)) {
    const stat = fs.lstatSync(PUBLIC_IMAGES);
    if (stat.isSymbolicLink()) {
      fs.unlinkSync(PUBLIC_IMAGES);
    }
  }

  fs.mkdirSync(PUBLIC_IMAGES, { recursive: true });

  const slugDirs = fs
    .readdirSync(IMAGES_DIR, { withFileTypes: true })
    .filter((d) => d.isDirectory() && d.name !== "thumbs" && d.name !== "full");

  for (const dir of slugDirs) {
    const slugPublic = path.join(PUBLIC_IMAGES, dir.name);
    fs.mkdirSync(slugPublic, { recursive: true });

    for (const sub of ["thumbs", "full"] as const) {
      const target = path.join(IMAGES_DIR, dir.name, sub);
      const link = path.join(slugPublic, sub);

      if (!fs.existsSync(target)) continue;

      // Remove stale link or directory
      try {
        fs.rmSync(link, { recursive: true, force: true });
      } catch {
        // doesn't exist yet, fine
      }

      fs.symlinkSync(target, link);
    }
  }
}

async function main() {
  if (!fs.existsSync(IMAGES_DIR)) {
    console.log("No images directory found, skipping image processing.");
    return;
  }

  const stats = await processImages();

  console.log(
    `Thumbnails (${THUMB_WIDTH}px): ${stats.thumbGenerated} generated, ${stats.thumbSkipped} already exist.`
  );
  console.log(
    `Full-size  (${FULL_WIDTH}px): ${stats.fullGenerated} generated, ${stats.fullSkipped} already exist.`
  );

  linkPublicImages();
  console.log("Linked processed images into public/images/.");
}

main().catch((err) => {
  console.error("Image processing failed:", err);
  process.exit(1);
});
