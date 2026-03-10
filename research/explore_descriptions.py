"""Feed sample descriptions to LLM agent and iterate on extraction schema."""

import asyncio
import json
from pathlib import Path

from rich.console import Console

from cca_archive.config import get_settings
from cca_archive.llm import extract_exhibition_metadata

SAMPLE_FILE = Path("research/sample_output/album_descriptions.json")
console = Console()


async def main() -> None:
    settings = get_settings()

    if not SAMPLE_FILE.exists():
        console.print(
            "[red]Run explore_albums.py first to generate sample descriptions.[/red]"
        )
        return

    with open(SAMPLE_FILE) as f:
        albums = json.load(f)

    # Process a sample of albums with descriptions
    samples = [a for a in albums if a.get("description", "").strip()][:10]
    console.print(f"Processing [cyan]{len(samples)}[/cyan] sample albums with descriptions\n")

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
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")

        console.print()


if __name__ == "__main__":
    asyncio.run(main())
