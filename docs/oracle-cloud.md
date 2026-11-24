# Run the bot 24/7 on Oracle Cloud's free tier (from Windows)

This guide takes about 30–45 minutes the first time. You'll end up with a small
Ubuntu server in Oracle's cloud that runs the bot all the time, restarts it if it
crashes or the server reboots, and backs up everyone's collections every day.

The bot only makes outgoing connections (to Discord, Scryfall, Moxfield, Archidekt),
so you **don't** need to open any firewall ports.

---

## 1. Create an Oracle Cloud account

1. Go to <https://www.oracle.com/cloud/free/> and click **Start for free**.
2. Fill in your details. Oracle asks for a credit card to verify you're a real person.
   Always Free resources are not charged.
3. Pick a **home region** close to you. You can't change it later, and Always Free
   servers can only be created in your home region.
4. Wait for the "your account is ready" email, then sign in at <https://cloud.oracle.com>.

## 2. Create the server (an "instance")

1. In the Oracle console, open the menu (☰) → **Compute** → **Instances** → **Create instance**.
2. **Name:** `mtgbot`.
3. **Image and shape** → **Edit**:
   - **Image:** click **Change image** → **Ubuntu** → pick **Canonical Ubuntu 24.04**
     (not the "Minimal" one, and not 20.04 or 22.04; the list shows several versions).
     Before clicking **Create**, check the Image line on the main form says 24.04.
   - **Shape:** click **Change shape**. Either works, and both show an *Always Free-eligible* tag:
     - **Ampere** → `VM.Standard.A1.Flex`, 1 OCPU and 6 GB memory. Faster, but often
       says "Out of capacity". If so, try again later or use the next option.
     - **Specialty and previous generation** → `VM.Standard.E2.1.Micro` (AMD, 1 GB memory).
       Plenty for this bot and usually available.
4. **Networking:** leave the defaults (a new virtual cloud network, public IPv4 address assigned).
5. **Add SSH keys:** choose **Generate a key pair for me**, then click **Save private key**
   (and optionally **Save public key**). Keep the private key file safe. It's how you log
   in, and Oracle can't give it to you again.
6. Click **Create**. After a minute the status turns green (**Running**). Copy the
   **Public IP address** from the instance page.

## 3. Connect from Windows

Windows 10 and 11 already include SSH. Open **PowerShell** (Start → type "PowerShell").

1. Move the key somewhere tidy and lock down its permissions (SSH refuses keys that
   other accounts can read). Change the file name if yours differs:

   ```powershell
   mkdir $HOME\.ssh -Force
   move $HOME\Downloads\ssh-key-*.key $HOME\.ssh\oracle-mtgbot.key
   icacls $HOME\.ssh\oracle-mtgbot.key /inheritance:r /grant:r "$($env:USERNAME):R"
   ```

2. Connect, using the public IP you copied:

   ```powershell
   ssh -i $HOME\.ssh\oracle-mtgbot.key ubuntu@YOUR.PUBLIC.IP
   ```

   Type `yes` the first time it asks about the fingerprint. Your prompt changes to
   something like `ubuntu@mtgbot:~$`. You're now typing commands on the server.

   Tip: to make this shorter next time, add this to `C:\Users\<you>\.ssh\config`
   (create the file if needed), and then just run `ssh mtgbot`:

   ```
   Host mtgbot
       HostName YOUR.PUBLIC.IP
       User ubuntu
       IdentityFile ~/.ssh/oracle-mtgbot.key
   ```

## 4. Let the server download your private repo

The repo is private, so the server needs its own read-only key for it (a "deploy key").
On the **server**:

```bash
ssh-keygen -t ed25519 -C "mtgbot-server" -f ~/.ssh/github_deploy -N ""
cat ~/.ssh/github_deploy.pub
printf 'Host github.com\n  IdentityFile ~/.ssh/github_deploy\n' >> ~/.ssh/config
```

Copy the line that starts with `ssh-ed25519`. On GitHub, open the repo →
**Settings** → **Deploy keys** → **Add deploy key**. Title it `oracle server`, paste the
line, leave **Allow write access** unticked, and click **Add key**.

## 5. Download and install the bot

Still on the server:

```bash
git clone git@github.com:bpeizer/discordmtgcollections.git ~/DiscordMTGCollections
cd ~/DiscordMTGCollections
bash deploy/install.sh
```

Type `yes` if git asks whether to trust github.com. The install script takes a few
minutes. It installs Python, sets up the bot, registers it as a service that starts on
boot, and schedules a daily backup.

## 6. Put your bot token on the server

Your token only ever goes in this one file on the server. Don't paste it into chat,
GitHub, or anywhere else.

```bash
nano ~/DiscordMTGCollections/.env
```

Replace `paste-your-bot-token-here` with your token (in PowerShell, right-click pastes).
Save with **Ctrl+O**, **Enter**, then exit with **Ctrl+X**. If you want `[[Card Name]]`
lookups, also remove the `#` in front of `ENABLE_BRACKET_LOOKUP=true` (and turn on
**Message Content Intent** in the Discord developer portal).

Start the bot:

```bash
sudo systemctl start mtgbot
sudo systemctl status mtgbot
```

You want to see **active (running)**. Press `q` to leave the status screen. Try
`/whohas` in Discord. You can now close PowerShell, and the bot keeps running.

## Everyday tasks

| I want to… | Run on the server |
|---|---|
| See if it's running | `sudo systemctl status mtgbot` |
| Watch the live log | `journalctl -u mtgbot -f` (Ctrl+C to stop watching) |
| See the last 100 log lines | `journalctl -u mtgbot -n 100 --no-pager` |
| Restart it | `sudo systemctl restart mtgbot` |
| Stop it | `sudo systemctl stop mtgbot` |
| Update to the latest code from GitHub | `cd ~/DiscordMTGCollections && bash deploy/update.sh` |
| Back up right now | `~/DiscordMTGCollections/deploy/backup.sh` |
| Change the token or settings | `nano ~/DiscordMTGCollections/.env`, then restart |

`update.sh` makes a backup first, pulls the new code, installs any new packages, and
restarts the bot.

## Backups

Every night at 04:15 (server time, which is UTC) the server copies `collections.db` into
`~/DiscordMTGCollections/backups/` and keeps the newest 14 copies. Those copies are on
the same server, so also pull one to your PC now and then. In **PowerShell on Windows**
(not on the server):

```powershell
mkdir $HOME\mtgbot-backups -Force
scp -i $HOME\.ssh\oracle-mtgbot.key "ubuntu@YOUR.PUBLIC.IP:DiscordMTGCollections/backups/*.db" $HOME\mtgbot-backups\
```

**To restore** a backup on the server:

```bash
sudo systemctl stop mtgbot
cp ~/DiscordMTGCollections/backups/collections-YYYYMMDD-HHMMSS.db ~/DiscordMTGCollections/collections.db
sudo systemctl start mtgbot
```

## Troubleshooting

- **"Out of capacity" when creating an Ampere server:** use `VM.Standard.E2.1.Micro`
  instead, or try Ampere again at a different time of day.
- **`Permission denied (publickey,gssapi-keyex,gssapi-with-mic)`:** the server is probably
  running Oracle Linux (its user is `opc`), meaning the Ubuntu image wasn't selected.
  Terminate it and create it again with Ubuntu 24.04.
- **`Permission denied (publickey)` when connecting:** check the IP, that the user is
  `ubuntu`, and that you ran the `icacls` command on the key file.
- **No public IP shown:** instance → **Networking** → the VNIC → **IP administration** →
  ⋮ on the private IP → **Edit** → **Ephemeral public IP** → **Update**.
- **Welcome message says Ubuntu 20.04 or 22.04:** the wrong image version was picked. The
  install script stops with a Python version error. Recreate the server with 24.04.
- **`git clone` says permission denied:** the deploy key wasn't added on GitHub, or the
  `~/.ssh/config` line from step 4 is missing. Test with `ssh -T git@github.com`.
- **Status shows `failed` or keeps restarting:** run `journalctl -u mtgbot -n 50 --no-pager`.
  `DISCORD_TOKEN is missing` or `Improper token` means the `.env` file needs fixing.
- **Slash commands don't show up:** they can take up to an hour the first time. Setting
  `DEV_GUILD_ID` in `.env` and restarting makes them appear right away in that server.
- **Oracle idle reclamation:** Oracle may stop Always Free servers it considers idle for a
  long stretch. This bot is light, so it's possible. If your server is ever stopped,
  start it again from the Instances page; your files are kept. Upgrading the account to
  Pay As You Go (still free if you stay within Always Free limits) avoids this.
