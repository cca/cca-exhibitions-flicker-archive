"""LLM extraction agent using pydantic-ai."""

from pydantic_ai import Agent

from .config import Settings
from .models import ExhibitionMetadata

SYSTEM_PROMPT = """\
You are an archivist specializing in contemporary art exhibitions. You are given
the title and description text of a Flickr photo album from the CCA (Center for
Contemporary Art / California College of the Arts) exhibitions account.

Extract structured exhibition metadata from the text. The description may be
informal, incomplete, or contain HTML tags — do your best to parse it.

Guidelines:
- exhibition_title: Use the album title as a starting point, but prefer a more
  formal exhibition title if one is clearly stated in the description.
- artists: List individual artist names. If it's a group show, list all named artists.
- curator: The person credited as curator, if mentioned.
- venue: The specific gallery or space (e.g., "Wattis Institute", "CCA Hubbell Street Galleries").
- opening_date / closing_date: Exhibition run dates if mentioned.
- reception_date: Opening reception date/time if mentioned.
- medium: Artistic medium(s) if described (e.g., "photography", "mixed media installation").
- description_summary: A 1-2 sentence summary of the exhibition, if enough info exists.
- raw_description: Always pass through the original description text unchanged.

If a field cannot be determined from the text, leave it as null.
"""


def create_agent(settings: Settings) -> Agent[None, ExhibitionMetadata]:
    """Create a pydantic-ai agent for exhibition metadata extraction."""
    return Agent(
        model=settings.llm_model,
        output_type=ExhibitionMetadata,
        system_prompt=SYSTEM_PROMPT,
    )


async def extract_exhibition_metadata(
    description: str,
    album_title: str,
    settings: Settings,
) -> ExhibitionMetadata:
    """Extract exhibition metadata from album description using LLM."""
    if not description or not description.strip():
        return ExhibitionMetadata(
            exhibition_title=album_title,
            raw_description=description or "",
        )

    agent = create_agent(settings)
    user_prompt = f"Album title: {album_title}\n\nAlbum description:\n{description}"
    result = await agent.run(user_prompt)
    return result.output
