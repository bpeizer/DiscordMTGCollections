"""Reading collections from Moxfield, Archidekt, and CSV/text exports.

Moxfield and Archidekt have no official public collection API. The endpoints
below are the ones their own websites call, so they may change or block bots
without notice. Each fetcher returns {card name: quantity}.
"""
import csv
import io
import re
from dataclasses import dataclass

from . import scryfall
from .http import Http

MAX_PAGES = 500  # safety stop (~50k distinct cards)


@dataclass
class Link:
    source: str  # 'moxfield' or 'archidekt'
    id: str
    url: str


_MOX = re.compile(r"moxfield\.com/collection/([A-Za-z0-9_-]+)", re.I)
_ARCH = re.compile(r"archidekt\.com/collection/(?:v2/)?(\d+)", re.I)


def parse_link(url: str) -> Link | None:
    url = url.strip().strip("<>")
    if m := _MOX.search(url):
        return Link("moxfield", m.group(1), url)
    if m := _ARCH.search(url):
        return Link("archidekt", m.group(1), url)
    return None


def _add(out: dict[str, int], name: str | None, qty) -> None:
    if not name:
        return
    try:
        q = int(qty)
    except (TypeError, ValueError):
        q = 1
    out[name] = out.get(name, 0) + max(q, 0)


# ---- Moxfield ---------------------------------------------------------
async def fetch_moxfield(http: Http, collection_id: str) -> dict[str, int]:
    url = f"https://api2.moxfield.com/v1/collections/search/{collection_id}"
    out: dict[str, int] = {}
    pending_ids: list[tuple[str, int]] = []
    page = 1
    while page <= MAX_PAGES:
        data = await http.get_json(url, {
            "pageNumber": page, "pageSize": 100,
            "sortColumn": "cardName", "sortDirection": "ascending"})
        for entry in data.get("data", []):
            if entry.get("game", "paper") != "paper":
                continue
            card = entry.get("card") or {}
            qty = entry.get("quantity", 1)
            if card.get("name"):
                _add(out, card["name"], qty)
            elif card.get("scryfall_id"):
                pending_ids.append((card["scryfall_id"], qty))
        total_pages = data.get("totalPages")
        if total_pages is None:
            total = data.get("totalResults", 0)
            total_pages = -(-total // 100)
        if page >= total_pages or not data.get("data"):
            break
        page += 1
    if pending_ids:  # some responses only carry Scryfall ids
        names = await scryfall.names_for_ids(http, [i for i, _ in pending_ids])
        for sid, qty in pending_ids:
            _add(out, names.get(sid), qty)
    return out


# ---- Archidekt --------------------------------------------------------
def _archidekt_name(entry: dict) -> str | None:
    card = entry.get("card") or {}
    oracle = card.get("oracleCard") or {}
    return oracle.get("name") or card.get("name") or entry.get("name")


async def fetch_archidekt(http: Http, user_id: str) -> dict[str, int]:
    url = f"https://archidekt.com/api/collection/v2/{user_id}/"
    out: dict[str, int] = {}
    params: dict | None = {"page": 1, "pageSize": 100}
    for _ in range(MAX_PAGES):
        data = await http.get_json(url, params)
        rows = data.get("results") or data.get("items") or []
        for entry in rows:
            _add(out, _archidekt_name(entry), entry.get("quantity", 1))
        nxt = data.get("next")
        if not nxt or not rows:
            break
        url, params = nxt, None  # 'next' is a full URL with its own query
    return out


async def fetch(http: Http, link: Link) -> dict[str, int]:
    if link.source == "moxfield":
        return await fetch_moxfield(http, link.id)
    if link.source == "archidekt":
        return await fetch_archidekt(http, link.id)
    raise ValueError(link.source)


# ---- CSV / text fallback ---------------------------------------------
_NAME_COLS = ("name", "card name", "card", "cardname")
_QTY_COLS = ("count", "quantity", "qty", "amount")  # "Amount" = Mythic Tools/MythicHub
_LINE = re.compile(r"^\s*(\d+)\s*x?\s+(.+?)\s*(?:\(\w+\).*)?$", re.I)


def parse_export(text: str) -> dict[str, int]:
    """Parse a CSV export (Moxfield, Archidekt, Deckbox, ManaBox, Mythic Tools,
    ...) or a
    plain list like '4 Lightning Bolt'."""
    text = text.lstrip("﻿")
    first = text.splitlines()[0].lower() if text.strip() else ""
    out: dict[str, int] = {}
    if "," in first and any(c in first for c in _NAME_COLS):
        reader = csv.DictReader(io.StringIO(text))
        cols = {c.lower().strip(): c for c in reader.fieldnames or []}
        name_col = next((cols[c] for c in _NAME_COLS if c in cols), None)
        qty_col = next((cols[c] for c in _QTY_COLS if c in cols), None)
        status_col = cols.get("status")            # Mythic: Owned / Sold
        binder_type_col = cols.get("binder type")  # ManaBox: binder / deck / list
        for row in reader:
            if status_col and (row.get(status_col) or "").strip().lower() == "sold":
                continue
            if binder_type_col and (row.get(binder_type_col) or "").strip().lower() in ("list", "wishlist"):
                continue  # ManaBox "lists" are usually wishlists, not owned cards
            _add(out, (row.get(name_col) or "").strip(), row.get(qty_col, 1) if qty_col else 1)
        return out
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith(("#", "//")):
            continue
        if m := _LINE.match(line):
            _add(out, m.group(2), m.group(1))
        else:
            _add(out, line, 1)
    return out
