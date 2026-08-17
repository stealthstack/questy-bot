# QuestSpeed Bot

A Discord bot for a Pokémon Quest speedrunning community. It serves community speedrun records and runs a "daily pot" Pokémon-claiming minigame, all through `discord.py` commands and interactive button-based UI Views.

## Features

- `!speedrun [category]`: show a random speedrun record, optionally filtered by category (e.g. `12-Boss`, `Any%`)
- `!collection [index]`: browse the Pokémon you've claimed from the daily pot
- `!dailypot`: claim one of 3 randomly selected speedrun Pokémon; shared per-day pot with per-user cooldowns
- `!devpot`: developer variant of the daily pot flow
- `!storage`: view the available power stones
- `!ping`: basic latency check

Speedrun records are rendered as Discord embeds with a composited image of the run's Pokémon thumbnail and equipped stones, built on the fly with Pillow.

## Setup

1. Install dependencies:
   ```
   pip install -r requirements.txt
   ```
2. Create a Discord bot application and copy its token from the [Discord Developer Portal](https://discord.com/developers/applications).
3. Copy `.env.example` to `.env` and fill in your token:
   ```
   DISCORD_BOT_TOKEN=your-bot-token-here
   ```
4. Run the bot:
   ```
   python speedrun_bot.py
   ```

## Data pipeline

Speedrun records live in `speedrun_data.csv` (the hand-maintained source of truth). Run `extract_csv.py` to regenerate `speedrun_data.json`, which the bot loads at startup:

```
python extract_csv.py
```

`archive/download_images.py` is the one-time setup script that originally fetched the stone and Pokémon thumbnail images now committed under `images/`. It's not needed to run the bot; kept only for reference in case those images ever need re-fetching (requires `requests`, not in `requirements.txt`).

`speedrun_data_meta.json` holds a single `data_as_of` date shown in record embed footers so the community knows how fresh the leaderboard is. Update it whenever the CSV is refreshed. Records aren't deleted over time, just re-statused (e.g. a `PB` becoming `Legacy` once beaten), so one dataset-wide date is enough; no per-record timestamps needed.

## Notes

- `daily_pot_claims.json` is runtime state (per-user cooldowns and collections) and is git-ignored; it's generated automatically the first time `!dailypot` runs.
- See `TODO.md` for in-progress refactor work.
