# Recipe Bot

Personal Telegram bot that sends 6 real recipe suggestions every Thursday at 18:00 (London time). Reply with the numbers you want and it instantly generates a grouped Sainsbury's shopping list.

## How it works

1. You build a library of real recipes using `/add <url>` or `/addmanual`
2. Every Thursday at 18:00 the bot messages you with 6 suggestions chosen by an LLM (variety, no recent repeats)
3. You reply with numbers (e.g. `1 3 5`)
4. The bot replies with a grouped shopping list

## Setup

### 1. Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/getting-started/installation/)
- A Telegram bot token from [@BotFather](https://t.me/botfather)
- An OpenAI API key

### 2. Install dependencies

```bash
uv sync
```

### 3. Configure environment

```bash
cp .env.example .env
```

Fill in your `.env`:

```
TELEGRAM_BOT_TOKEN=your_token_here
TELEGRAM_CHAT_ID=your_chat_id_here
OPENAI_API_KEY=your_key_here
```

> **Don't know your chat ID?** Leave `TELEGRAM_CHAT_ID` as a placeholder, run the bot, send `/start` to it in Telegram, and it will reply with your real chat ID. Update `.env` and restart.

### 4. Run

```bash
uv run python bot.py
```

## Commands

| Command | Description |
|---|---|
| `/add <url>` | Scrape and save a recipe from a website |
| `/addmanual` | Add a recipe step-by-step (for Instagram etc.) |
| `/list` | Browse your recipe library |
| `/suggest` | Trigger this week's suggestions immediately |
| `/status` | Show library size, last run time |
| `/start` | Show help and your chat ID |

## Adding recipes

**From a website** — works with 500+ sites (BBC Good Food, Mob Kitchen, Bosh, Jamie Oliver, RecipeTin Eats, etc.):
```
/add https://www.bbcgoodfood.com/recipes/...
```

**From Instagram or anywhere else** — use the guided manual flow:
```
/addmanual
```

## Deployment (Railway)

1. Push this repo to GitHub
2. Create a new project on [Railway](https://railway.app) and connect the repo
3. Add the three environment variables in Railway's dashboard
4. Deploy — Railway uses `railway.toml` automatically

The bot uses long polling so no webhook or open port is needed.

## Data

Everything is stored in `recipes.json` — human-readable and git-trackable. The file contains your recipe library, recently used recipes (last 4 weeks), and the last run timestamp.
