"""Turn what a user typed into a card name and find who owns it."""
import difflib

from . import scryfall
from .db import Store
from .http import Http


async def find(store: Store, http: Http, guild_id: int, query: str):
    """Returns (card_name, rows, suggestions)."""
    query = query.strip().strip("[]").strip()
    rows = store.who_has(guild_id, query)
    if rows:
        return rows[0]["name"], rows, []
    name = await scryfall.canonical_name(http, query)
    if name:
        rows = store.who_has(guild_id, name)
        if rows:
            return rows[0]["name"], rows, []
    # Nothing exact: suggest close names that people here actually own.
    close = difflib.get_close_matches(query, store.all_names(guild_id), n=3, cutoff=0.6)
    return name or query, [], close


def format_owners(card: str, rows, suggestions) -> str:
    if rows:
        total = sum(r["qty"] for r in rows)
        lines = [f"**{card}**: {total} cop{'y' if total == 1 else 'ies'} across "
                 f"{len(rows)} member{'s' if len(rows) != 1 else ''}"]
        lines += [f"• <@{r['user_id']}> × {r['qty']}" for r in rows[:25]]
        if len(rows) > 25:
            lines.append(f"…and {len(rows) - 25} more")
        return "\n".join(lines)
    msg = f"Nobody here has **{card}** in a linked collection."
    if suggestions:
        msg += " Did you mean: " + ", ".join(f"**{s}**" for s in suggestions) + "?"
    return msg
