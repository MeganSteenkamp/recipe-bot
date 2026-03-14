import logging
import os
import re

import pytz
import telebot
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from dotenv import load_dotenv

from llm import generate_shopping_list, select_recipes
from recipes import add_recipe, get_recently_used, get_recipes, load_data, mark_used
from scraper import scrape_recipe

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = int(os.environ["TELEGRAM_CHAT_ID"])
LONDON_TZ = pytz.timezone("Europe/London")

bot = telebot.TeleBot(BOT_TOKEN, parse_mode=None)

# Maps chat_id -> list of 6 recipe dicts that were suggested this week.
# Cleared once the user replies with their choices.
pending_suggestions: dict = {}

# Maps chat_id -> {"step": str, "data": dict} for the /addmanual flow.
pending_manual: dict = {}

MANUAL_STEPS = ["title", "creator", "cook_time", "ingredients", "servings"]
MANUAL_PROMPTS = {
    "title":       "What's the recipe title?",
    "creator":     "Who's the creator or source? (e.g. Mob Kitchen, @username)",
    "cook_time":   "Roughly how long does it take? (e.g. 30 min, 1 h) — or reply 'skip'",
    "ingredients": "Paste the ingredients, one per line:",
    "servings":    "How many servings? (e.g. 4) — or reply 'skip'",
}


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


@bot.message_handler(commands=["start", "help"])
def handle_start(message):
    bot.reply_to(
        message,
        (
            "👋 Recipe bot is running!\n\n"
            f"Your chat ID: {message.chat.id}\n\n"
            "Commands:\n"
            "/add <url>     — add a recipe from a website\n"
            "/addmanual     — add a recipe manually (e.g. from Instagram)\n"
            "/list          — browse your recipe library\n"
            "/suggest       — trigger this week's suggestions now\n"
            "/status        — show bot status\n\n"
            "Every Thursday at 18:00 London time I'll send you 6 recipe suggestions. "
            "Just reply with the numbers you want (e.g. 1 3 5) and I'll build your shopping list."
        ),
    )


@bot.message_handler(commands=["add"])
def handle_add(message):
    parts = message.text.strip().split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip():
        bot.reply_to(message, "Usage: /add <recipe_url>")
        return

    url = parts[1].strip()
    bot.reply_to(message, f"Scraping {url} ...")

    try:
        recipe = scrape_recipe(url)
    except Exception as e:
        logger.error(f"Scrape failed for {url}: {e}")
        bot.reply_to(
            message,
            (
                f"Could not scrape that URL.\n\n"
                f"Error: {e}\n\n"
                "Make sure it's a direct recipe page on a supported site "
                "(Bosh, Mob Kitchen, BBC Good Food, Jamie Oliver, etc.)."
            ),
        )
        return

    added = add_recipe(recipe)
    if added:
        ingredient_count = len(recipe["ingredients"])
        cook_time = recipe.get("cook_time") or "unknown"
        bot.reply_to(
            message,
            (
                f"Added: {recipe['title']} — {recipe['creator']}\n"
                f"Cook time: {cook_time} | {ingredient_count} ingredients"
            ),
        )
    else:
        bot.reply_to(message, "That URL is already in your library.")


@bot.message_handler(commands=["list"])
def handle_list(message):
    recipes = get_recipes()
    if not recipes:
        bot.reply_to(message, "No recipes yet. Use /add <url> to add some!")
        return

    lines = [
        f"{i + 1}. {r['title']} — {r['creator']} ({r.get('cook_time') or '?'})"
        for i, r in enumerate(recipes)
    ]
    text = f"Your recipe library ({len(recipes)} recipes):\n\n" + "\n".join(lines)
    # Telegram message limit is 4096 chars; split if needed
    for chunk in _split_message(text):
        bot.reply_to(message, chunk)


@bot.message_handler(commands=["status"])
def handle_status(message):
    data = load_data()
    recipes = data["recipes"]
    recently_used = data["recently_used"]
    last_run = data.get("last_run") or "Never"
    bot.reply_to(
        message,
        (
            "Bot Status\n\n"
            f"Recipes in library: {len(recipes)}\n"
            f"Recently used (last 4 weeks): {len(recently_used)}\n"
            f"Last Thursday run: {last_run}\n"
            "Next run: Thursday 18:00 London time"
        ),
    )


@bot.message_handler(commands=["suggest"])
def handle_suggest(message):
    _send_weekly_suggestions(message.chat.id)


@bot.message_handler(commands=["addmanual"])
def handle_addmanual(message):
    chat_id = message.chat.id
    pending_manual[chat_id] = {"step": "title", "data": {}}
    bot.reply_to(message, MANUAL_PROMPTS["title"])


# ---------------------------------------------------------------------------
# Reply handler — manual entry flow + number selections
# ---------------------------------------------------------------------------


@bot.message_handler(func=lambda m: True)
def handle_reply(message):
    chat_id = message.chat.id

    # --- Manual entry flow takes priority ---
    if chat_id in pending_manual:
        _handle_manual_step(message)
        return

    if chat_id not in pending_suggestions:
        return  # Nothing pending; ignore

    numbers = [int(n) for n in re.findall(r"\d+", message.text)]
    if not numbers:
        return

    suggestions = pending_suggestions[chat_id]
    valid = [n for n in numbers if 1 <= n <= len(suggestions)]
    if not valid:
        bot.reply_to(
            message, f"Please reply with numbers between 1 and {len(suggestions)}."
        )
        return

    # Deduplicate while preserving order
    seen: set = set()
    chosen_indices = [n - 1 for n in valid if not (n in seen or seen.add(n))]
    chosen = [suggestions[i] for i in chosen_indices]

    bot.reply_to(message, "Building your shopping list...")

    try:
        shopping = generate_shopping_list(chosen)
    except Exception as e:
        logger.error(f"Shopping list generation failed: {e}")
        bot.reply_to(message, f"Failed to generate shopping list: {e}")
        return

    chosen_lines = "\n".join(
        f"{valid[i]}. {chosen[i]['title']} — {chosen[i]['creator']} "
        f"(approx. {chosen[i].get('cook_time') or '?'})"
        for i in range(len(chosen))
    )
    plural = "s" if len(chosen) != 1 else ""
    response = (
        f"Your {len(chosen)} chosen meal{plural}:\n\n"
        f"{chosen_lines}\n\n"
        f"{'─' * 34}\n"
        f"Sainsbury's Shopping List\n\n"
        f"{shopping}"
    )

    for chunk in _split_message(response):
        bot.reply_to(message, chunk)

    mark_used([r["title"] for r in chosen])
    del pending_suggestions[chat_id]


# ---------------------------------------------------------------------------
# Weekly suggestion job
# ---------------------------------------------------------------------------


def _handle_manual_step(message) -> None:
    chat_id = message.chat.id
    state = pending_manual[chat_id]
    step = state["step"]
    text = message.text.strip()

    if step == "ingredients":
        # Split on newlines; filter blank lines
        value = [line.strip() for line in text.splitlines() if line.strip()]
    elif text.lower() == "skip":
        value = None
    else:
        value = text

    state["data"][step] = value

    # Advance to next step
    current_index = MANUAL_STEPS.index(step)
    if current_index + 1 < len(MANUAL_STEPS):
        next_step = MANUAL_STEPS[current_index + 1]
        state["step"] = next_step
        bot.reply_to(message, MANUAL_PROMPTS[next_step])
    else:
        # All steps done — save the recipe
        d = state["data"]
        if not d.get("ingredients"):
            bot.reply_to(message, "No ingredients provided — recipe not saved. Start again with /addmanual.")
            del pending_manual[chat_id]
            return

        recipe = {
            "url": f"manual:{d['title'].lower().replace(' ', '-')}",
            "title": d["title"],
            "creator": d["creator"],
            "site": "manual",
            "added": __import__("datetime").date.today().isoformat(),
            "ingredients": d["ingredients"],
            "instructions": "",
            "cook_time": d.get("cook_time"),
            "servings": d.get("servings"),
        }

        added = add_recipe(recipe)
        del pending_manual[chat_id]

        if added:
            bot.reply_to(
                message,
                (
                    f"Saved: {recipe['title']} — {recipe['creator']}\n"
                    f"Cook time: {recipe['cook_time'] or '?'} | {len(recipe['ingredients'])} ingredients"
                ),
            )
        else:
            bot.reply_to(message, "A recipe with that title already exists in your library.")


def _send_weekly_suggestions(chat_id: int) -> None:
    recipes = get_recipes()
    if len(recipes) < 6:
        bot.send_message(
            chat_id,
            (
                f"You only have {len(recipes)} recipe(s) in your library. "
                "Add at least 6 with /add <url> so I can send proper suggestions."
            ),
        )
        return

    recently_used = get_recently_used()

    try:
        suggestion_text = select_recipes(recipes, recently_used)
    except Exception as e:
        logger.error(f"LLM selection failed: {e}")
        bot.send_message(chat_id, f"Failed to generate suggestions: {e}")
        return

    suggested_recipes = _match_suggestions_to_library(suggestion_text, recipes)

    if len(suggested_recipes) < 2:
        # Fallback: send the text anyway and store first 6 library recipes
        logger.warning(
            f"Could only match {len(suggested_recipes)} suggestions to library entries; using fallback."
        )
        pending_suggestions[chat_id] = recipes[:6]
    else:
        pending_suggestions[chat_id] = suggested_recipes

    bot.send_message(
        chat_id,
        (
            "Here are this week's 6 real recipes I think you'll love\n"
            "Reply with the numbers you want (e.g. 1 3 5)\n\n"
            f"{suggestion_text}"
        ),
    )


def _match_suggestions_to_library(suggestion_text: str, recipes: list) -> list:
    """Match LLM output titles back to library recipe dicts."""
    matched = []
    for line in suggestion_text.splitlines():
        m = re.match(r"^\d+\.\s+(.+?)\s+[—–-]", line)
        if not m:
            continue
        suggested_title = m.group(1).strip().lower()

        best = None
        # Exact match first
        for recipe in recipes:
            if recipe["title"].lower() == suggested_title:
                best = recipe
                break
        # Partial match fallback
        if not best:
            for recipe in recipes:
                lib_title = recipe["title"].lower()
                if suggested_title in lib_title or lib_title in suggested_title:
                    best = recipe
                    break

        if best and best not in matched:
            matched.append(best)

    return matched


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _split_message(text: str, limit: int = 4000) -> list:
    """Split a long message into chunks that fit within Telegram's limit."""
    if len(text) <= limit:
        return [text]
    chunks = []
    while text:
        chunks.append(text[:limit])
        text = text[limit:]
    return chunks


# ---------------------------------------------------------------------------
# Scheduler
# ---------------------------------------------------------------------------


def start_scheduler() -> BackgroundScheduler:
    scheduler = BackgroundScheduler(timezone=LONDON_TZ)
    scheduler.add_job(
        lambda: _send_weekly_suggestions(CHAT_ID),
        CronTrigger(day_of_week="thu", hour=18, minute=0, timezone=LONDON_TZ),
        id="weekly_suggestions",
        replace_existing=True,
    )
    scheduler.start()
    logger.info("Scheduler started — suggestions every Thursday at 18:00 London time.")
    return scheduler


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


if __name__ == "__main__":
    logger.info("Starting Recipe Bot...")
    try:
        _send_weekly_suggestions(CHAT_ID)
    except Exception as e:
        logger.error(f"Startup send failed (bad CHAT_ID?): {e}")
    bot.infinity_polling(logger_level=logging.INFO)
