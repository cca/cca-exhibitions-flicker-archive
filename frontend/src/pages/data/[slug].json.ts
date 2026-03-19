import type { APIRoute, GetStaticPaths } from "astro";
import { getAllAlbums } from "../../lib/data";

export const getStaticPaths: GetStaticPaths = () => {
  const albums = getAllAlbums();
  return albums.map((album) => ({
    params: { slug: album.slug },
  }));
};

export const GET: APIRoute = ({ params }) => {
  const album = getAllAlbums().find((a) => a.slug === params.slug);

  if (!album) {
    return new Response(JSON.stringify({ error: "Album not found" }), {
      status: 404,
      headers: { "Content-Type": "application/json" },
    });
  }

  const data = {
    slug: album.slug,
    exhibition_title: album.exhibition_title,
    venue: album.venue,
    opening_date: album.opening_date,
    artists: album.artists,
    photos: album.photos.map((photo) => ({
      photo_id: photo.photo_id,
      image_src: photo.image_src,
      photo_title: photo.photo_title,
    })),
  };

  return new Response(JSON.stringify(data), {
    headers: { "Content-Type": "application/json" },
  });
};
