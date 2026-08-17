# QuestSpeed Bot

A Discord bot for a Pokémon Quest speedrunning community. It serves community speedrun records and runs a "daily pot" Pokémon-claiming minigame — all through `discord.py` commands and interactive button-based UI Views.

## Features

- `!speedrun [category]` — show a random speedrun record, optionally filtered by category (e.g. `12-Boss`, `Any%`)
- `!collection [index]` — browse the Pokémon you've claimed from the daily pot
- `!dailypot` — claim one of 3 randomly selected speedrun Pokémon; shared per-day pot with per-user cooldowns
- `!devpot` — developer variant of the daily pot flow
- `!storage` — view the available power stones
- `!ping` — basic latency check

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

`download_images.py` is a one-time setup script that fetches the stone and Pokémon thumbnail images used in embeds into `images/`.

## Notes

- `daily_pot_claims.json` is runtime state (per-user cooldowns and collections) and is git-ignored — it's generated automatically the first time `!dailypot` runs.
- See `TODO.md` for in-progress refactor work.
