"""Discord bot entry point. Run with:  python -m mtgbot.bot"""
import asyncio
import logging
import os
import re
import time

import discord
from discord import app_commands
from discord.ext import tasks
from dotenv import load_dotenv

from . import scryfall, sources
from .db import Store
from .http import Http, HttpError
from .lookup import find, format_owners

load_dotenv()
log = logging.getLogger("mtgbot")

TOKEN = os.environ.get("DISCORD_TOKEN")
DB_PATH = os.environ.get("DB_PATH", "collections.db")
SYNC_HOURS = float(os.environ.get("SYNC_HOURS", "12"))
BRACKETS = os.environ.get("ENABLE_BRACKET_LOOKUP", "false").lower() in ("1", "true", "yes")
DEV_GUILD = os.environ.get("DEV_GUILD_ID")  # optional: instant command sync to one server
MAX_UPLOAD = 5 * 1024 * 1024
NO_PINGS = discord.AllowedMentions.none()
BRACKET_RE = re.compile(r"\[\[([^\[\]]{2,150})\]\]")


class MTGBot(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = BRACKETS  # privileged; only needed for [[card]]
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)
        self.store = Store(DB_PATH)
        self.http_client = Http()

    async def setup_hook(self):
        self.tree.add_command(collection)
        self.tree.add_command(whohas)
        if DEV_GUILD:
            guild = discord.Object(id=int(DEV_GUILD))
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
        else:
            await self.tree.sync()
        self.resync.start()

    async def close(self):
        await self.http_client.close()
        await super().close()

    async def sync_member(self, guild_id: int, user_id: int, link: sources.Link) -> int:
        try:
            cards = await sources.fetch(self.http_client, link)
        except HttpError as e:
            self.store.record_error(guild_id, user_id, str(e))
            raise
        return self.store.replace_collection(guild_id, user_id, link.source, link.url, cards)

    @tasks.loop(minutes=30)
    async def resync(self):
        for row in self.store.links_due(time.time() - SYNC_HOURS * 3600):
            link = sources.parse_link(row["url"] or "")
            if not link:
                continue
            try:
                await self.sync_member(row["guild_id"], row["user_id"], link)
            except Exception as e:  # keep going for everyone else
                log.warning("resync failed for %s: %s", row["user_id"], e)
            await asyncio.sleep(2)

    @resync.before_loop
    async def _wait_ready(self):
        await self.wait_until_ready()

    async def on_message(self, message: discord.Message):
        if not BRACKETS or message.author.bot or not message.guild:
            return
        names = BRACKET_RE.findall(message.content)[:5]
        if not names:
            return
        replies = []
        for n in names:
            card, rows, sugg = await find(self.store, self.http_client, message.guild.id, n)
            replies.append(format_owners(card, rows, sugg))
        await message.reply("\n\n".join(replies)[:2000], allowed_mentions=NO_PINGS)


bot = MTGBot()

# ---- /collection ------------------------------------------------------
collection = app_commands.Group(name="collection", description="Manage your card collection",
                                guild_only=True)


def _err_text(e: Exception, source: str) -> str:
    if isinstance(e, HttpError) and e.status in (401, 403):
        return (f"{source.title()} refused the request (HTTP {e.status}). Make sure the collection "
                f"is public. If it is, {source.title()} may be blocking bots right now; "
                "you can use `/collection upload` with a CSV export instead.")
    if isinstance(e, HttpError) and e.status == 404:
        return f"{source.title()} says that collection doesn't exist. Check the link."
    return f"Couldn't read the collection from {source.title()}: {e}"


@collection.command(name="link", description="Link a public Moxfield or Archidekt collection")
@app_commands.describe(url="e.g. https://moxfield.com/collection/AbC123 or https://archidekt.com/collection/v2/12345")
async def collection_link(inter: discord.Interaction, url: str):
    link = sources.parse_link(url)
    if not link:
        await inter.response.send_message(
            "That doesn't look like a Moxfield or Archidekt collection link.", ephemeral=True)
        return
    await inter.response.defer(ephemeral=True, thinking=True)
    try:
        n = await bot.sync_member(inter.guild_id, inter.user.id, link)
    except Exception as e:
        await inter.followup.send(_err_text(e, link.source), ephemeral=True)
        return
    await inter.followup.send(
        f"Linked your {link.source.title()} collection: {n} different cards. "
        f"I'll re-sync it about every {SYNC_HOURS:g} hours, or run `/collection sync`.",
        ephemeral=True)


@collection.command(name="sync", description="Re-read your linked collection now")
async def collection_sync(inter: discord.Interaction):
    row = bot.store.link(inter.guild_id, inter.user.id)
    link = sources.parse_link(row["url"]) if row and row["url"] else None
    if not link:
        await inter.response.send_message("You haven't linked a collection. Use `/collection link`.",
                                          ephemeral=True)
        return
    await inter.response.defer(ephemeral=True, thinking=True)
    try:
        n = await bot.sync_member(inter.guild_id, inter.user.id, link)
        await inter.followup.send(f"Synced: {n} different cards.", ephemeral=True)
    except Exception as e:
        await inter.followup.send(_err_text(e, link.source), ephemeral=True)


@collection.command(name="upload", description="Upload a CSV export (ManaBox, Mythic Tools, Moxfield, Archidekt, Deckbox...)")
async def collection_upload(inter: discord.Interaction, file: discord.Attachment):
    if file.size > MAX_UPLOAD:
        await inter.response.send_message("That file is over 5 MB.", ephemeral=True)
        return
    await inter.response.defer(ephemeral=True, thinking=True)
    text = (await file.read()).decode("utf-8", errors="replace")
    cards = sources.parse_export(text)
    if not cards:
        await inter.followup.send("I couldn't find any cards in that file.", ephemeral=True)
        return
    n = bot.store.replace_collection(inter.guild_id, inter.user.id, "csv", None, cards)
    await inter.followup.send(f"Saved {n} different cards from {file.filename}. "
                              "This replaces any linked collection.", ephemeral=True)


@collection.command(name="info", description="Show what the bot has saved for you")
async def collection_info(inter: discord.Interaction):
    row = bot.store.link(inter.guild_id, inter.user.id)
    if not row:
        await inter.response.send_message("Nothing saved for you yet.", ephemeral=True)
        return
    distinct, total = bot.store.stats(inter.guild_id, inter.user.id)
    when = f"<t:{int(row['last_synced'])}:R>" if row["last_synced"] else "never"
    msg = f"Source: {row['source']}\nCards: {distinct} different, {total} total\nLast synced: {when}"
    if row["url"]:
        msg += f"\nLink: {row['url']}"
    if row["last_error"]:
        msg += f"\nLast sync error: {row['last_error']}"
    await inter.response.send_message(msg, ephemeral=True)


@collection.command(name="unlink", description="Delete your saved collection from this server")
async def collection_unlink(inter: discord.Interaction):
    bot.store.clear(inter.guild_id, inter.user.id)
    await inter.response.send_message("Your collection has been removed.", ephemeral=True)


# ---- /whohas ----------------------------------------------------------
@app_commands.command(name="whohas", description="See which members own a card")
@app_commands.describe(card="Card name (typos are OK)")
@app_commands.guild_only()
async def whohas(inter: discord.Interaction, card: str):
    await inter.response.defer(thinking=True)
    name, rows, sugg = await find(bot.store, bot.http_client, inter.guild_id, card)
    await inter.followup.send(format_owners(name, rows, sugg), allowed_mentions=NO_PINGS)


@whohas.autocomplete("card")
async def whohas_autocomplete(inter: discord.Interaction, current: str):
    if len(current) < 2:
        return []
    names = bot.store.suggest(inter.guild_id, current)
    if len(names) < 5:
        names += [n for n in await scryfall.autocomplete(bot.http_client, current) if n not in names]
    return [app_commands.Choice(name=n[:100], value=n[:100]) for n in names[:25]]


def main():
    logging.basicConfig(level=logging.INFO)
    if not TOKEN:
        raise SystemExit("DISCORD_TOKEN is missing. Put it in a .env file next to this project.")
    bot.run(TOKEN)


if __name__ == "__main__":
    main()
