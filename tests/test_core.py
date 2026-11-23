import asyncio

from mtgbot import sources
from mtgbot.db import Store
from mtgbot.lookup import find, format_owners


class FakeHttp:
    """Serves canned JSON keyed by URL; records calls."""
    def __init__(self, pages=None, posts=None, named=None):
        self.pages, self.posts, self.named, self.calls = pages or {}, posts or {}, named or {}, []

    async def get_json(self, url, params=None):
        self.calls.append((url, params))
        if url.endswith("/cards/named"):
            from mtgbot.http import HttpError
            if params["fuzzy"] in self.named:
                return {"name": self.named[params["fuzzy"]]}
            raise HttpError(404, url)
        key = (url, (params or {}).get("pageNumber") or (params or {}).get("page"))
        return self.pages[key]

    async def post_json(self, url, body):
        return {"data": [{"id": i["id"], "name": self.posts[i["id"]]} for i in body["identifiers"]]}


def run(c):
    return asyncio.run(c)


def test_parse_link():
    assert sources.parse_link("https://moxfield.com/collection/AbC-12_x").id == "AbC-12_x"
    l = sources.parse_link("<https://archidekt.com/collection/v2/4242>")
    assert (l.source, l.id) == ("archidekt", "4242")
    assert sources.parse_link("https://moxfield.com/decks/abc") is None


def test_moxfield_paging_and_scryfall_ids():
    base = "https://api2.moxfield.com/v1/collections/search/X"
    http = FakeHttp(pages={
        (base, 1): {"totalPages": 2, "data": [
            {"quantity": 4, "game": "paper", "card": {"name": "Lightning Bolt"}},
            {"quantity": 1, "game": "arena", "card": {"name": "Arena Only"}}]},
        (base, 2): {"totalPages": 2, "data": [
            {"quantity": 2, "card": {"scryfall_id": "sid1"}},
            {"quantity": 1, "card": {"name": "Lightning Bolt"}}]},
    }, posts={"sid1": "Sol Ring"})
    assert run(sources.fetch_moxfield(http, "X")) == {"Lightning Bolt": 5, "Sol Ring": 2}


def test_archidekt_follows_next():
    base = "https://archidekt.com/api/collection/v2/7/"
    nxt = base + "?page=2"
    http = FakeHttp(pages={
        (base, 1): {"next": nxt, "results": [
            {"quantity": 3, "card": {"oracleCard": {"name": "Counterspell"}}}]},
        (nxt, None): {"next": None, "results": [
            {"quantity": 1, "card": {"oracleCard": {"name": "Counterspell"}}}]},
    })
    assert run(sources.fetch_archidekt(http, "7")) == {"Counterspell": 4}


def test_parse_csv_and_text():
    mox = 'Count,Tradelist Count,Name,Edition\n"4","0","Lightning Bolt","m10"\n"1","0","Sol Ring","c21"\n'
    assert sources.parse_export(mox) == {"Lightning Bolt": 4, "Sol Ring": 1}
    manabox = "Name,Set code,Quantity\nCounterspell,mh2,2\n"
    assert sources.parse_export(manabox) == {"Counterspell": 2}
    txt = "4 Lightning Bolt (M10) 146\n1x Sol Ring\nBrainstorm\n"
    assert sources.parse_export(txt) == {"Lightning Bolt": 4, "Sol Ring": 1, "Brainstorm": 1}


def test_lookup_end_to_end():
    s = Store(":memory:")
    s.replace_collection(1, 100, "moxfield", "u", {"Lightning Bolt": 4,
                                                  "Delver of Secrets // Insectile Aberration": 1})
    s.replace_collection(1, 200, "archidekt", "u", {"lightning bolt": 1})
    s.replace_collection(2, 300, "csv", None, {"Lightning Bolt": 9})  # other server
    http = FakeHttp(named={"lightnig bolt": "Lightning Bolt"})

    card, rows, _ = run(find(s, http, 1, "lightnig bolt"))
    assert [(r["user_id"], r["qty"]) for r in rows] == [(100, 4), (200, 1)]
    assert "5 copies across 2 members" in format_owners(card, rows, [])

    _, rows, _ = run(find(s, http, 1, "[[Delver of Secrets]]"))
    assert [r["user_id"] for r in rows] == [100]

    _, rows, sugg = run(find(s, http, 1, "Lightning Bolts"))
    assert rows == [] and sugg == ["Lightning Bolt"]

    s.replace_collection(1, 100, "moxfield", "u", {"Sol Ring": 1})  # re-sync replaces
    _, rows, _ = run(find(s, http, 1, "Lightning Bolt"))
    assert [r["user_id"] for r in rows] == [200]


def test_manabox_and_mythic_exports():
    manabox = ("Binder Name,Binder Type,Name,Set code,Set name,Collector number,Foil,Rarity,Quantity,ManaBox ID,Scryfall ID\n"
               "Trade binder,binder,Sol Ring,c21,Commander 2021,263,normal,uncommon,2,1,abc\n"
               "My deck,deck,Sol Ring,cmm,Commander Masters,410,foil,uncommon,1,2,def\n"
               "Wants,list,Mana Crypt,2xm,Double Masters,270,normal,mythic,1,3,ghi\n")
    assert sources.parse_export(manabox) == {"Sol Ring": 3}
    mythic = ("Amount,Name,Set Code,Set Name,Collector Number,Condition,Finish,Language,Status,Binder\n"
              "4,Counterspell,mh2,Modern Horizons 2,267,NM,Nonfoil,EN,Owned,Blue\n"
              "1,Counterspell,7ed,Seventh Edition,67,LP,Nonfoil,EN,Sold,Blue\n")
    assert sources.parse_export(mythic) == {"Counterspell": 4}
