import fs from "node:fs";
import path from "node:path";
import sharp from "sharp";
import pLimit from "p-limit";

const PROJECT_ROOT = path.resolve(import.meta.dirname, "../..");
const IMAGES_DIR = path.join(PROJECT_ROOT, "output/images");
const THUMB_WIDTH = 400;
const THUMB_QUALITY = 75;
const CONCURRENCY = 8;

async function main() {
  if (!fs.existsSync(IMAGES_DIR)) {
    console.log("No images directory found, skipping thumbnail generation.");
    return;
  }

  const slugDirs = fs
    .readdirSync(IMAGES_DIR, { withFileTypes: true })
    .filter((d) => d.isDirectory() && d.name !== "thumbs");

  const limit = pLimit(CONCURRENCY);
  const tasks: Promise<void>[] = [];
  let generated = 0;
  let skipped = 0;

  for (const dir of slugDirs) {
    const slugPath = path.join(IMAGES_DIR, dir.name);
    const thumbsDir = path.join(slugPath, "thumbs");

    const files = fs
      .readdirSync(slugPath)
      .filter((f) => /\.(jpe?g|png)$/i.test(f));

    if (files.length === 0) continue;

    for (const file of files) {
      const id = path.parse(file).name;
      const srcPath = path.join(slugPath, file);
      const destPath = path.join(thumbsDir, `${id}.webp`);

      if (fs.existsSync(destPath)) {
        skipped++;
        continue;
      }

      tasks.push(
        limit(async () => {
          fs.mkdirSync(thumbsDir, { recursive: true });
          await sharp(srcPath)
            .resize({ width: THUMB_WIDTH })
            .webp({ quality: THUMB_QUALITY })
            .toFile(destPath);
          generated++;
        })
      );
    }
  }

  await Promise.all(tasks);
  console.log(
    `Thumbnails: ${generated} generated, ${skipped} skipped (already exist).`
  );
}

main().catch((err) => {
  console.error("Thumbnail generation failed:", err);
  process.exit(1);
});
