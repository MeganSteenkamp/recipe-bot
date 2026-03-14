import json
import os
from datetime import date
from urllib.parse import urlparse

from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
MODEL = "gpt-4o-mini"


def extract_recipe_from_text(url: str, page_text: str) -> dict:
    """Extract a recipe dict from raw page text using the LLM."""
    system = """\
You are a recipe extraction assistant. Given the raw text of a recipe webpage, extract the recipe details.
Respond ONLY with a valid JSON object — no markdown, no extra text.

JSON fields (use null for anything missing):
{
  "title": "string",
  "ingredients": ["string", ...],
  "instructions": "string",
  "cook_time": "string (e.g. '30 min', '1 h')",
  "servings": "string (e.g. 'Serves 4')"
}"""

    resp = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": f"URL: {url}\n\nPage text:\n{page_text}"},
        ],
        temperature=0,
        max_tokens=1200,
    )
    data = json.loads(resp.choices[0].message.content.strip())

    site = urlparse(url).netloc.replace("www.", "")
    return {
        "url": url,
        "title": data["title"],
        "creator": site,
        "site": site,
        "added": date.today().isoformat(),
        "ingredients": data.get("ingredients") or [],
        "instructions": data.get("instructions") or "",
        "cook_time": data.get("cook_time"),
        "servings": data.get("servings"),
        "image": None,
    }


def select_recipes(recipes: list, recently_used: list) -> str:
    """Ask the LLM to pick 6 recipes from the library for this week."""
    recipes_summary = "\n".join(
        f"- {r['title']} — {r['creator']} | Cook time: {r.get('cook_time') or 'unknown'} | Servings: {r.get('servings') or 'unknown'}"
        for r in recipes
    )
    recent = (
        "\n".join(f"- {r['title']} (used {r['used_on']})" for r in recently_used)
        or "None"
    )

    system = """\
You are my personal meal planner.
You ONLY use REAL published recipes from the exact library below.
Never invent, adapt or combine recipes.

Rules – strict:
• Select exactly 6 DIFFERENT recipes from my library
• Maximise variety: different cuisines, proteins/veg focus, effort levels
• Avoid anything in the recently_used list
• Prioritise recipes I have not eaten recently
• Choose meals that feel exciting for a weeknight but realistic
• Keep each description to 1 short, appetising sentence

Output format ONLY – nothing else:

1. [Exact Title] — [Creator]
   [One sentence why I'll love it this week]
   (≈ [time])

2. …"""

    user = f"My library right now:\n{recipes_summary}\n\nRecently eaten (do NOT pick these):\n{recent}"

    resp = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=0.7,
        max_tokens=900,
    )
    return resp.choices[0].message.content.strip()


def generate_shopping_list(chosen_recipes: list) -> str:
    """Generate a grouped Sainsbury's shopping list from the chosen recipes."""
    recipes_text = "\n\n".join(
        f"{r['title']} — {r['creator']}\nIngredients:\n"
        + "\n".join(f"• {i}" for i in r["ingredients"])
        for r in chosen_recipes
    )

    system = """\
You are a helpful meal prep assistant. Given a list of recipes and their exact ingredients, \
create a combined, grouped Sainsbury's shopping list.

Rules:
• Use ONLY the exact ingredients listed — never add extras
• Combine duplicates and sum quantities where sensible
• Group by supermarket aisle category using these headings (use only the ones needed):
  🥦 Fresh Vegetables
  🍎 Fresh Fruit
  🧄 Fresh Herbs & Aromatics
  🥩 Meat & Fish
  🧀 Dairy & Alternatives
  🥚 Eggs
  🥫 Tins & Jars
  🌾 Dry Goods & Pasta
  🍞 Bread & Bakery
  🧴 Condiments & Oils
  🌶️ Herbs & Spices
  ❄️ Frozen
• List each item as: • [quantity] [item]
• End with a single line: "Approx total cook time: ~X hours spread across the week"

Output the shopping list ONLY — no preamble, no sign-off."""

    user = f"Create a grouped Sainsbury's shopping list for these recipes:\n\n{recipes_text}"

    resp = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=0.2,
        max_tokens=1400,
    )
    return resp.choices[0].message.content.strip()
