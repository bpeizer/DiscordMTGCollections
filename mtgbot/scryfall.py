"""Scryfall lookups: canonical card names and Scryfall-id -> name resolution."""
from .http import Http, HttpError

API = "https://api.scryfall.com"


async def canonical_name(http: Http, query: str) -> str | None:
    """Fuzzy-match what the user typed ('lightnig bolt') to a real card name."""
    try:
        card = await http.get_json(f"{API}/cards/named", {"fuzzy": query})
        return card.get("name")
    except HttpError:
        return None


async def autocomplete(http: Http, query: str) -> list[str]:
    try:
        data = await http.get_json(f"{API}/cards/autocomplete", {"q": query})
        return data.get("data", [])
    except HttpError:
        return []


async def names_for_ids(http: Http, ids: list[str]) -> dict[str, str]:
    """Resolve Scryfall card ids to names, 75 at a time (the API's limit)."""
    out: dict[str, str] = {}
    unique = list(dict.fromkeys(ids))
    for i in range(0, len(unique), 75):
        chunk = unique[i:i + 75]
        data = await http.post_json(f"{API}/cards/collection",
                                    {"identifiers": [{"id": x} for x in chunk]})
        for card in data.get("data", []):
            out[card["id"]] = card["name"]
    return out
