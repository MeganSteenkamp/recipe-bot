import json
import os
from datetime import date, datetime, timedelta

RECIPES_FILE = os.path.join(os.path.dirname(__file__), "recipes.json")


def load_data() -> dict:
    if not os.path.exists(RECIPES_FILE):
        return {"recipes": [], "recently_used": [], "last_run": None}
    with open(RECIPES_FILE) as f:
        return json.load(f)


def save_data(data: dict) -> None:
    with open(RECIPES_FILE, "w") as f:
        json.dump(data, f, indent=2)


def add_recipe(recipe: dict) -> bool:
    """Add a recipe. Returns False if the URL already exists."""
    data = load_data()
    if any(r["url"] == recipe["url"] for r in data["recipes"]):
        return False
    data["recipes"].append(recipe)
    save_data(data)
    return True


def get_recipes() -> list:
    return load_data()["recipes"]


def get_recently_used() -> list:
    return load_data()["recently_used"]


def mark_used(titles: list) -> None:
    """Record chosen recipe titles and prune entries older than 4 weeks."""
    data = load_data()
    today = date.today().isoformat()
    for title in titles:
        data["recently_used"].append({"title": title, "used_on": today})
    cutoff = (date.today() - timedelta(days=28)).isoformat()
    data["recently_used"] = [r for r in data["recently_used"] if r["used_on"] >= cutoff]
    data["last_run"] = datetime.utcnow().isoformat() + "Z"
    save_data(data)
