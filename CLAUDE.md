# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A single-file Discord bot (`speedrun_bot.py`) for a Pokémon Quest speedrunning community. It serves speedrun records and runs a "daily pot" Pokémon-claiming minigame — all via `!`-prefixed commands and `discord.py` UI Views/Buttons. There is no test suite, build step, or package manifest; this is a small, actively-hacked-on script, not a packaged project.

## Running the bot

```
pip install -r requirements.txt
python speedrun_bot.py
```

The bot reads its token from the `DISCORD_BOT_TOKEN` environment variable (loaded via `python-dotenv` from a local `.env`, see `.env.example`). It exits with a clear error if the variable isn't set. Never hardcode a token back into `speedrun_bot.py` — `.env` is git-ignored specifically to keep it out of version control.

## Data pipeline

Speedrun records flow: `speedrun_data.csv` (source of truth, hand-edited/exported) → `extract_csv.py` → `speedrun_data.json` (loaded into memory at startup as `SPEEDRUN_DB`). Re-run `extract_csv.py` after editing the CSV to regenerate the JSON that the bot actually reads. `speedrun_data.json` is never written back to by the bot itself. Note: `extract_csv.py`'s emoji `print()` calls crash on Windows under the default `cp1252` console encoding — run it with `PYTHONIOENCODING=utf-8` set, or fix the script, if you hit `UnicodeEncodeError`.

`speedrun_data_meta.json` holds one field, `data_as_of` (`YYYY-MM-DD`), shown in record embed footers as a dataset-wide freshness marker. Bump it whenever the CSV is refreshed; individual records aren't timestamped since they're never deleted, only re-statused (e.g. `PB` → `Legacy`).

`archive/download_images.py` fetched the stone/thumbnail PNGs now committed under `images/`, from Serebii and a third-party GitHub mirror. Already run, its output already committed; kept only for provenance/re-fetching, not called by the bot. Needs `requests`, which isn't in `requirements.txt` since nothing else uses it.

`daily_pot_claims.json` is runtime state (per-user cooldowns and collections, plus the current day's shared pot), read and rewritten on every relevant command. It is not sample data — treat it as a live database file.

## Architecture inside speedrun_bot.py

Everything lives in one module, organized by command:

- **Static lookups near the top**: `SPEEDRUN_DB` (loaded once from JSON), `STONE_FILES` (stone name → image path), `ITEMS`.
- **Shared embed/image helpers** (`create_composite_image`, `create_record_embed`): these are the *intended* single source of truth for building Discord embeds with composite stone images, but per `TODO.md` several commands (`dailypot`, `devpot`, `collection`) still have their own **inlined, duplicated copies** of this same compositing/embed logic rather than calling the helpers. When editing embed/image rendering behavior, check whether the change needs to be made in the shared helper, the duplicated inline copies, or both — don't assume the helper is actually being used everywhere it looks like it should be.
- **Commands** (`@bot.command`): `!speedrun`, `!ping`, `!storage`, `!collection`, `!dailypot`, `!devpot`.
- **Daily pot minigame**: `!dailypot` generates (or loads) a shared daily selection of 3 Pokémon records, tracks per-user 16-hour cooldowns and per-index claims in `daily_pot_claims.json`, and hands off to `DailyPotView` for the claim buttons — including "on cooldown but pot still has unclaimed slots" and dev-only pot-regeneration (hardcoded to one Discord user ID) branches.
- **`!devpot`/`DevPotView`** and **`!collection`/`CollectionView`** are parallel, largely independent variants of the same claim/browse pattern — check both when changing shared behavior like cooldowns, claim persistence, or embed layout.

## Known in-progress work

See `TODO.md`: the helper-function refactor (deduplicating the inline embed/image code in `dailypot`, `devpot`, and `collection` into the shared helpers already defined near the top of the file) is intentionally incomplete. If asked to continue that refactor, the unchecked items in `TODO.md` are the remaining scope.

An earlier "expedition" cooperative-battle feature (commands, an `Expedition` class, and `ExpeditionView`) was removed as unfinished/superseded — don't reintroduce it based on old references elsewhere.
