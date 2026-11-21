"""the shape every search provider returns."""
from dataclasses import dataclass


@dataclass
class SearchResult:
    url: str
    title: str
    snippet: str = ""
    content: str = ""  # cleaned page text when the provider supplies it (tavily)
