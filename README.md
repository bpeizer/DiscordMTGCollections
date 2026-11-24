# MTG Collections Discord bot

Members link their public Moxfield or Archidekt collection. Anyone can then ask
which members own a card.

| Command | What it does |
|---|---|
| `/whohas <card>` | Lists members who own the card and how many copies. Typos are OK, and card names autocomplete. |
| `/collection link <url>` | Links a public Moxfield (`moxfield.com/collection/...`) or Archidekt (`archidekt.com/collection/v2/...`) collection. Re-syncs about every 12 hours. |
| `/collection sync` | Re-reads your linked collection now. |
| `/collection upload <file>` | Upload a CSV export. This is how ManaBox and Mythic Tools users add their collection, since those apps have no public collection link. Also works for Moxfield, Archidekt, Deckbox, or a text list like `4 Lightning Bolt`. Re-upload to update. |
| `/collection info` | Shows what's saved for you and when it last synced. |
| `/collection unlink` | Deletes your saved collection from this server. |
| `[[Card Name]]` in chat | Optional, same as `/whohas`. Turn on with `ENABLE_BRACKET_LOOKUP=true`. |

Collections are kept per server, so a member links once in each server they use the bot in.
Replies show member names without pinging anyone.

## Setup

### 1. Create the bot in Discord
1. Go to https://discord.com/developers/applications and click **New Application**.
2. Open **Bot**, click **Reset Token**, and copy the token. Treat it like a password.
3. Only if you want `[[Card Name]]` lookups: on the same page, turn on **Message Content Intent**.
4. Open **OAuth2 → URL Generator**. Tick `bot` and `applications.commands`, then under
   bot permissions tick **Send Messages** and **Read Message History**. Open the generated
   URL and add the bot to your server.

### 2. Run it
Needs Python 3.10 or newer.

```bash
cd mtg-bot
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env             # Windows: copy .env.example .env
```

Open `.env` and paste your token after `DISCORD_TOKEN=`. The token stays on your machine
in that file; don't paste it anywhere else. Then:

```bash
python -m mtgbot.bot
```

Slash commands can take up to an hour to appear the first time. To see them right away
while testing, set `DEV_GUILD_ID` in `.env` to your server's id (Discord settings →
Advanced → Developer Mode, then right-click the server → Copy Server ID).

The bot keeps everything in `collections.db` next to it. Back that file up if you care
about it. The bot only runs while this command is running. To keep it online 24/7 for
free, follow **[docs/oracle-cloud.md](docs/oracle-cloud.md)**, which sets it up on an Oracle
Cloud Always Free server with automatic restarts and daily backups.

### Tests
```bash
pip install pytest && python -m pytest
```

## Exporting from apps without links
- **ManaBox:** Collection tab → top-right menu → Export → CSV. Cards in *lists* (usually wishlists) are skipped; binders and decks count.
- **Mythic Tools:** Settings → Export collection → CSV. Cards marked *Sold* are skipped.
- Then run `/collection upload` in Discord and attach the file.

## How card matching works
Names are compared after lowercasing and removing accents and punctuation. If the exact
name isn't found, the bot asks [Scryfall](https://scryfall.com/docs/api) for the closest real
card name (so `lightnig bolt` works). Double-faced cards match on their front face. If
nobody owns it, the bot suggests close names that people in the server do own.

## Known limits
- Moxfield and Archidekt don't publish an official collection API. The bot reads the same
  endpoints their websites use, which can change or be blocked without notice. If linking
  fails with a "refused" error, `/collection upload` with a CSV export always works.
- Collections must be set to public on the site.
