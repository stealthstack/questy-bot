# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A single-file Discord bot (`speedrun_bot.py`) for a Pokémon Quest speedrunning community. It serves speedrun records, runs a "daily pot" Pokémon-claiming minigame, and simulates group "expeditions" — all via `!`-prefixed commands and `discord.py` UI Views/Buttons. There is no test suite, build step, or package manifest; this is a small, actively-hacked-on script, not a packaged project.

## Running the bot

```
pip install -r requirements.txt
python speedrun_bot.py
```

The bot reads its token from the `DISCORD_BOT_TOKEN` environment variable (loaded via `python-dotenv` from a local `.env`, see `.env.example`). It exits with a clear error if the variable isn't set. Never hardcode a token back into `speedrun_bot.py` — `.env` is git-ignored specifically to keep it out of version control.

## Data pipeline

Speedrun records flow: `speedrun_data.csv` (source of truth, hand-edited/exported) → `extract_csv.py` → `speedrun_data.json` (loaded into memory at startup as `SPEEDRUN_DB`). Re-run `extract_csv.py` after editing the CSV to regenerate the JSON that the bot actually reads. `speedrun_data.json` is never written back to by the bot itself.

`download_images.py` fetches the stone/thumbnail PNGs in `images/` from Serebii and a third-party GitHub mirror — a one-off setup script, not something the bot calls at runtime.

`daily_pot_claims.json` is runtime state (per-user cooldowns and collections, plus the current day's shared pot), read and rewritten on every relevant command. It is not sample data — treat it as a live database file.

## Architecture inside speedrun_bot.py

Everything lives in one 1500+ line module, organized by command:

- **Static lookups near the top**: `SPEEDRUN_DB` (loaded once from JSON), `STONE_FILES` (stone name → image path), `ITEMS`.
- **Shared embed/image helpers** (`create_composite_image`, `create_record_embed`, `create_expedition_results_embed`): these are the *intended* single source of truth for building Discord embeds with composite stone images, but per `TODO.md` several commands (`dailypot`, `devpot`, `collection`) still have their own **inlined, duplicated copies** of this same compositing/embed logic rather than calling the helpers. When editing embed/image rendering behavior, check whether the change needs to be made in the shared helper, the duplicated inline copies, or both — don't assume the helper is actually being used everywhere it looks like it should be.
- **Commands** (`@bot.command`): `!speedrun`, `!ping`, `!storage`, `!expedition`, `!submitresults`, `!collection`, `!dailypot`, `!devpot`.
- **Stateful group activity**: the `Expedition` class plus `active_expeditions` (a module-global `channel_id -> Expedition` dict) model a multiplayer flow — start, join, ready-up, battle simulation, result submission — driven by `ExpeditionView` (a `discord.ui.View` with Join/Ready/etc. buttons) and the `!expedition`/`!submitresults` commands together. `expedition.set_results` parses a specific pasted-text format via regex; if that format changes, update the regex and the parsing logic together.
- **Daily pot minigame**: `!dailypot` generates (or loads) a shared daily selection of 3 Pokémon records, tracks per-user 16-hour cooldowns and per-index claims in `daily_pot_claims.json`, and hands off to `DailyPotView` for the claim buttons — including "on cooldown but pot still has unclaimed slots" and dev-only pot-regeneration (hardcoded to one Discord user ID) branches.
- **`!devpot`/`DevPotView`** and **`!collection`/`CollectionView`** are parallel, largely independent variants of the same claim/browse pattern — check both when changing shared behavior like cooldowns, claim persistence, or embed layout.

## Known in-progress work

See `TODO.md`: the helper-function refactor (deduplicating the inline embed/image code in `dailypot`, `devpot`, `collection`, and `submit_results`/`ExpeditionView.check_results` into the shared helpers already defined near the top of the file) is intentionally incomplete. If asked to continue that refactor, the unchecked items in `TODO.md` are the remaining scope.
