"""Survey all albums — print summary table and save descriptions."""

import json
from pathlib import Path

from rich.console import Console
from rich.table import Table

from cca_archive.config import get_settings
from cca_archive.flickr_client import FlickrClient

OUTPUT_DIR = Path("research/sample_output")
console = Console()


def _text(val) -> str:
    if isinstance(val, dict):
        return val.get("_content", "")
    return str(val) if val else ""


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    settings = get_settings()
    client = FlickrClient(settings)

    console.print("[bold]Fetching all albums...[/bold]")
    albums = client.get_all_albums()
    console.print(f"Found [cyan]{len(albums)}[/cyan] albums\n")

    table = Table(title="CCA Exhibitions Albums")
    table.add_column("#", style="dim", justify="right")
    table.add_column("ID", style="dim")
    table.add_column("Title", max_width=40)
    table.add_column("Photos", justify="right")
    table.add_column("Description Preview", max_width=60)

    descriptions = []
    for i, a in enumerate(albums, 1):
        title = _text(a.get("title"))
        desc = _text(a.get("description"))
        photos = str(a.get("photos", "?"))
        preview = desc[:80].replace("\n", " ") + ("..." if len(desc) > 80 else "")
        table.add_row(str(i), str(a["id"]), title, photos, preview)
        descriptions.append({
            "album_id": str(a["id"]),
            "title": title,
            "description": desc,
            "photo_count": a.get("photos", 0),
        })

    console.print(table)

    with open(OUTPUT_DIR / "album_descriptions.json", "w") as f:
        json.dump(descriptions, f, indent=2, ensure_ascii=False)
    console.print(f"\nSaved descriptions to {OUTPUT_DIR / 'album_descriptions.json'}")


if __name__ == "__main__":
    main()
