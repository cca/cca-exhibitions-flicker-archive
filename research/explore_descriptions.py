"""Feed sample descriptions to LLM agent and iterate on extraction schema."""

import argparse
import asyncio
import json
from pathlib import Path

from rich.console import Console
from rich.table import Table

from cca_archive.config import get_settings
from cca_archive.llm import extract_exhibition_metadata

SAMPLE_FILE = Path("research/sample_output/album_descriptions.json")
OUTPUT_DIR = Path("research/sample_output")
console = Console()

# Fields in ExhibitionMetadata that we track for the comparison table
TRACKED_FIELDS = [
    "exhibition_title",
    "artists",
    "curator",
    "venue",
    "opening_date",
    "closing_date",
    "reception_date",
    "medium",
    "description_summary",
]


def _is_populated(value) -> bool:
    """Check whether a metadata field has a non-null, non-empty value."""
    if value is None:
        return False
    if isinstance(value, list) and len(value) == 0:
        return False
    if isinstance(value, str) and not value.strip():
        return False
    return True


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Feed sample descriptions to LLM and iterate on extraction schema."
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Max number of albums to process (default: 10).",
    )
    parser.add_argument(
        "--album-id",
        type=str,
        default=None,
        help="Process only the album with this ID.",
    )
    parser.add_argument(
        "--save",
        action="store_true",
        help="Save extraction results to research/sample_output/extraction_results.json.",
    )
    args = parser.parse_args()

    settings = get_settings()

    if not SAMPLE_FILE.exists():
        console.print(
            "[red]Run explore_albums.py first to generate sample descriptions.[/red]"
        )
        return

    with open(SAMPLE_FILE) as f:
        albums = json.load(f)

    # Filter to albums with descriptions
    samples = [a for a in albums if a.get("description", "").strip()]

    # Apply --album-id filter
    if args.album_id:
        samples = [a for a in samples if a["album_id"] == args.album_id]
        if not samples:
            console.print(
                f"[red]No album found with ID {args.album_id} "
                f"(or it has no description).[/red]"
            )
            return
    else:
        samples = samples[: args.limit]

    console.print(
        f"Processing [cyan]{len(samples)}[/cyan] sample albums with descriptions\n"
    )

    results = []
    # Track field extraction across all albums for comparison table
    comparison_rows = []

    for a in samples:
        console.rule(f"[bold]{a['title']}[/bold]")
        console.print(f"[dim]Description:[/dim] {a['description'][:200]}...")
        console.print()

        try:
            metadata = await extract_exhibition_metadata(
                description=a["description"],
                album_title=a["title"],
                settings=settings,
            )
            console.print(metadata.model_dump_json(indent=2))
            results.append({
                "album_id": a["album_id"],
                "title": a["title"],
                "metadata": metadata.model_dump(mode="json"),
            })

            # Build row for comparison table
            row = {"title": a["title"]}
            for field in TRACKED_FIELDS:
                row[field] = _is_populated(getattr(metadata, field, None))
            comparison_rows.append(row)

        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")
            results.append({
                "album_id": a["album_id"],
                "title": a["title"],
                "error": str(e),
            })
            row = {"title": a["title"]}
            for field in TRACKED_FIELDS:
                row[field] = None  # unknown due to error
            comparison_rows.append(row)

        console.print()

    # Print comparison table
    if comparison_rows:
        console.print()
        console.rule("[bold]Field Extraction Summary[/bold]")
        comp_table = Table(title="Extracted vs Null Fields")
        comp_table.add_column("Album", max_width=35)
        for field in TRACKED_FIELDS:
            comp_table.add_column(field, justify="center", max_width=14)

        for row in comparison_rows:
            title = row["title"][:35]
            cells = []
            for field in TRACKED_FIELDS:
                val = row[field]
                if val is True:
                    cells.append("[green]yes[/green]")
                elif val is False:
                    cells.append("[dim]--[/dim]")
                else:
                    cells.append("[red]err[/red]")
            comp_table.add_row(title, *cells)

        # Add totals row
        totals = []
        for field in TRACKED_FIELDS:
            count = sum(1 for r in comparison_rows if r[field] is True)
            totals.append(f"{count}/{len(comparison_rows)}")
        comp_table.add_row("[bold]TOTAL[/bold]", *[f"[bold]{t}[/bold]" for t in totals])

        console.print(comp_table)

    # Save results if requested
    if args.save:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        save_path = OUTPUT_DIR / "extraction_results.json"
        with open(save_path, "w") as f:
            json.dump(results, f, indent=2, ensure_ascii=False, default=str)
        console.print(f"\nSaved extraction results to {save_path}")


if __name__ == "__main__":
    asyncio.run(main())
