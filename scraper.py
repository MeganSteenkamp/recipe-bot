from datetime import date
from urllib.parse import urlparse
from recipe_scrapers import scrape_me

# Map known domains to friendly creator names
CREATOR_MAP = {
    "bosh.tv": "Bosh",
    "mobkitchen.co.uk": "Mob Kitchen",
    "mob.co.uk": "Mob Kitchen",
    "ottolenghi.co.uk": "Ottolenghi",
    "jamieoliver.com": "Jamie Oliver",
    "bbcgoodfood.com": "BBC Good Food",
    "thehappypear.ie": "The Happy Pear",
    "deliciouslyella.com": "Deliciously Ella",
    "pinchofyum.com": "Pinch of Yum",
    "minimalistbaker.com": "Minimalist Baker",
    "seriouseats.com": "Serious Eats",
    "thesortedguys.com": "Sorted Food",
    "sortedfood.com": "Sorted Food",
    "eatwell101.com": "EatWell101",
    "recipetineats.com": "RecipeTin Eats",
    "halfbakedharvest.com": "Half Baked Harvest",
    "budgetbytes.com": "Budget Bytes",
    "cookieandkate.com": "Cookie and Kate",
    "themodernproper.com": "The Modern Proper",
}


def _extract_site(url: str) -> str:
    return urlparse(url).netloc.replace("www.", "")


def _format_minutes(minutes) -> str:
    if not minutes:
        return None
    try:
        minutes = int(minutes)
    except (TypeError, ValueError):
        return str(minutes)
    if minutes < 60:
        return f"{minutes} min"
    hours, mins = divmod(minutes, 60)
    return f"{hours} h {mins} min" if mins else f"{hours} h"


def scrape_recipe(url: str) -> dict:
    scraper = scrape_me(url)

    site = _extract_site(url)
    creator = CREATOR_MAP.get(site, site)

    try:
        cook_time = _format_minutes(scraper.total_time())
    except Exception:
        cook_time = None

    try:
        servings = scraper.yields()
    except Exception:
        servings = None

    return {
        "url": url,
        "title": scraper.title(),
        "creator": creator,
        "site": site,
        "added": date.today().isoformat(),
        "ingredients": scraper.ingredients(),
        "instructions": scraper.instructions(),
        "cook_time": cook_time,
        "servings": servings,
    }
