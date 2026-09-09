"""Import NYC restaurants from OSM Overpass API and enrich with Google Maps Places API (New)."""
import argparse
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
from dotenv import load_dotenv
from difflib import SequenceMatcher

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
OUT_FILE = DATA_DIR / "eat_real.json"

NYC_BBOX = (40.4774, -74.2591, 40.9176, -73.7004)

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
OVERPASS_QUERY = """
[out:json][timeout:120];
(
  node["amenity"="restaurant"]({south},{west},{north},{east});
  way["amenity"="restaurant"]({south},{west},{north},{east});
  relation["amenity"="restaurant"]({south},{west},{north},{east});
);
out body center;
"""

GOOGLE_PLACES_API = "https://places.googleapis.com/v1/places:searchText"

FIELD_MASK = (
    "places.id,places.displayName,places.formattedAddress,places.location,"
    "places.priceLevel,places.rating,places.googleMapsUri,places.types"
)


PRICE_LEVEL_MAP = {
    0: {"label": "Free", "range": "$0", "budget_estimate": 0},
    1: {"label": "$", "range": "$10–20", "budget_estimate": 15},
    2: {"label": "$$", "range": "$20–40", "budget_estimate": 30},
    3: {"label": "$$$", "range": "$40–70", "budget_estimate": 55},
    4: {"label": "$$$$", "range": "$70+", "budget_estimate": 85},
}

DIETARY_TAGS = {
    "diet:vegetarian": "Vegetarian",
    "diet:vegan": "Vegan",
    "diet:gluten_free": "Gluten-free",
    "diet:halal": "Halal",
    "diet:kosher": "Kosher",
}

CUISINE_NORMALIZE = {
    "pizza": "Pizza",
    "italian": "Italian",
    "chinese": "Chinese",
    "japanese": "Japanese",
    "sushi": "Japanese",
    "mexican": "Mexican",
    "indian": "Indian",
    "american": "American",
    "burger": "American",
    "burgers": "American",
    "thai": "Thai",
    "korean": "Korean",
    "vietnamese": "Vietnamese",
    "mediterranean": "Mediterranean",
    "greek": "Mediterranean",
    "middle_eastern": "Mediterranean",
    "french": "French",
    "seafood": "Seafood",
    "steakhouse": "Steakhouse",
    "bbq": "BBQ",
    "barbecue": "BBQ",
    "vegetarian": "Vegetarian",
    "vegan": "Vegan",
    "cafe": "Cafe",
    "coffee_shop": "Cafe",
    "bakery": "Bakery",
    "delicatessen": "Deli",
    "sandwich": "Sandwich",
    "bagel": "Bagel",
    "donut": "Donut",
    "ice_cream": "Ice Cream",
    "dessert": "Dessert",
}


def normalize_cuisine(raw: str | None) -> list[str]:
    if not raw:
        return []
    cuisines = [c.strip().lower() for c in raw.split(";") if c.strip()]
    normalized = []
    for c in cuisines:
        norm = CUISINE_NORMALIZE.get(c, c.title())
        if norm not in normalized:
            normalized.append(norm)
    return normalized


def extract_dietary_options(tags: dict[str, str]) -> list[str]:
    options = []
    for tag, label in DIETARY_TAGS.items():
        if tags.get(tag) in ("yes", "only", "true", "1"):
            options.append(label)
    return options


def build_address(tags: dict[str, str]) -> str:
    parts = []
    if "addr:housenumber" in tags:
        parts.append(tags["addr:housenumber"])
    if "addr:street" in tags:
        parts.append(tags["addr:street"])
    if "addr:city" in tags:
        parts.append(tags["addr:city"])
    elif "addr:suburb" in tags:
        parts.append(tags["addr:suburb"])
    if "addr:postcode" in tags:
        parts.append(tags["addr:postcode"])
    if "addr:state" in tags:
        parts.append(tags["addr:state"])
    return ", ".join(parts) if parts else "New York, NY"


def get_coordinates(element: dict) -> tuple[float, float] | None:
    if element["type"] == "node":
        return (element["lat"], element["lon"])
    if "center" in element:
        return (element["center"]["lat"], element["center"]["lon"])
    return None


def osm_element_to_restaurant(element: dict) -> dict | None:
    tags = element.get("tags", {})
    name = tags.get("name") or tags.get("brand")
    if not name:
        return None

    coords = get_coordinates(element)
    if not coords:
        return None

    osm_id = element["id"]
    osm_type = element["type"]

    cuisine = normalize_cuisine(tags.get("cuisine"))
    dietary = extract_dietary_options(tags)
    address = build_address(tags)

    return {
        "id": f"osm_{osm_type}_{osm_id}",
        "title": name,
        "cuisine": cuisine,
        "dietary_options": dietary,
        "location": {"lat": coords[0], "lng": coords[1]},
        "address": address,
        "description": f"{name} — {address}",
        "source_url": f"https://www.openstreetmap.org/{osm_type}/{osm_id}",
        "provenance": {
            "source": "osm",
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
            "osm_id": osm_id,
            "osm_type": osm_type,
            "enriched_by": None,
            "enriched_at": None,
            "google_place_id": None,
        },
    }


def google_search_text(query: str, api_key: str) -> dict | None:
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": FIELD_MASK,
    }
    payload = {"textQuery": query, "maxResultCount": 5}
    with httpx.Client(timeout=30.0) as client:
        resp = client.post(GOOGLE_PLACES_API, headers=headers, json=payload)
        resp.raise_for_status()
        data = resp.json()
        places = data.get("places", [])
        if not places:
            return None
        return places[0]


def enrich_with_google(restaurant: dict, api_key: str) -> dict:
    query = f"{restaurant['title']} {restaurant['address']}"
    place = google_search_text(query, api_key)
    if not place:
        return restaurant

    place_id = place.get("id")
    # Text Search already returned the requested fields; avoid a second paid call.
    location = place.get('location', {})
    original = restaurant['location']
    from categories.eat import haversine_km
    if 'latitude' not in location or 'longitude' not in location:
        return restaurant
    if haversine_km(original['lat'], original['lng'], location['latitude'], location['longitude']) > .2:
        return restaurant
    if SequenceMatcher(None, restaurant['title'].casefold(), place.get('displayName', {}).get('text', '').casefold()).ratio() < .65:
        return restaurant
    details = place

    price_level = {"PRICE_LEVEL_FREE": 0, "PRICE_LEVEL_INEXPENSIVE": 1, "PRICE_LEVEL_MODERATE": 2, "PRICE_LEVEL_EXPENSIVE": 3, "PRICE_LEVEL_VERY_EXPENSIVE": 4}.get(details.get("priceLevel"))
    price_info = PRICE_LEVEL_MAP.get(price_level, {"label": "Unknown", "range": "Price unknown", "budget_estimate": None})

    editorial = details.get("editorialSummary", {})
    description = editorial.get("text", "")[:500] if editorial else ""

    photos = details.get("photos", [])
    photo_refs = [p.get("name") for p in photos if p.get("name")]

    opening_hours = details.get("currentOpeningHours", {})
    weekday_desc = opening_hours.get("weekdayDescriptions", []) if opening_hours else []

    google_types = details.get("types", [])
    cuisine_from_google = [t.replace("_", " ").title() for t in google_types if t not in (
        "restaurant", "food", "point_of_interest", "establishment"
    )]

    merged_cuisine = list(dict.fromkeys(restaurant["cuisine"] + cuisine_from_google))

    restaurant.update({
        "description": description or f"{restaurant['title']} - {restaurant['address']}",
        "price_level": price_level,
        "price_range": price_info["range"],
        "budget_estimate": price_info["budget_estimate"],
        "rating": details.get("rating"),
        "source_url": details.get("googleMapsUri") or restaurant["source_url"],
        "website_url": details.get("websiteUri"),
        "phone": details.get("nationalPhoneNumber"),
        "opening_hours": weekday_desc,
        "photos": photo_refs,
        "cuisine": merged_cuisine,
        "provenance": {
            **restaurant["provenance"],
            "enriched_by": "google_maps",
            "enriched_at": datetime.now(timezone.utc).isoformat(),
            "google_place_id": place_id,
        },
    })
    return restaurant


def fetch_osm_restaurants(bbox: tuple[float, float, float, float], limit: int | None = None) -> list[dict]:
    south, west, north, east = bbox
    query = OVERPASS_QUERY.format(south=south, west=west, north=north, east=east)
    print(f"Querying Overpass API for restaurants in bbox ({south}, {west}, {north}, {east})...")
    with httpx.Client(timeout=120.0) as client:
        resp = client.get(OVERPASS_URL, params={"data": query}, headers={"User-Agent": "OverlapHackathonDemo/1.0"})
        resp.raise_for_status()
        data = resp.json()

    elements = data.get("elements", [])
    print(f"Found {len(elements)} OSM elements")

    restaurants = []
    for el in elements:
        rest = osm_element_to_restaurant(el)
        if rest:
            restaurants.append(rest)
        if limit and len(restaurants) >= limit:
            break

    print(f"Normalized to {len(restaurants)} restaurants")
    return restaurants


def enrich_restaurants(restaurants: list[dict], api_key: str, delay: float = 0.2) -> list[dict]:
    enriched = []
    for i, rest in enumerate(restaurants, 1):
        print(f"[{i}/{len(restaurants)}] Enriching: {rest['title'][:50]}...")
        try:
            enriched_rest = enrich_with_google(rest, api_key)
            enriched.append(enriched_rest)
        except Exception as e:
            print(f"  Warning: enrichment failed ({type(e).__name__}); keeping OSM record.")
            enriched.append(rest)
        time.sleep(delay)
    return enriched


def main():
    load_dotenv(ROOT / ".env")
    parser = argparse.ArgumentParser(description="Import NYC restaurants from OSM + Google Maps")
    parser.add_argument("--bbox", default="40.4774,-74.2591,40.9176,-73.7004", help="Bounding box: south,west,north,east")
    parser.add_argument("--limit", type=int, default=50, help="Limit number of restaurants")
    parser.add_argument("--delay", type=float, default=0.2, help="Delay between Google API calls (seconds)")
    parser.add_argument("--output", default=str(OUT_FILE), help="Output JSON file")
    parser.add_argument("--api-key", default=os.getenv("GOOGLE_MAPS_API_KEY"), help="Google Maps API key")
    args = parser.parse_args()

    # Google enrichment is optional; OSM records remain usable with unknown prices.

    try:
        bbox = tuple(map(float, args.bbox.split(",")))
    except ValueError:
        parser.error("Bounding box coordinates must be numbers")
    if len(bbox) != 4:
        print("Error: bbox must be 4 comma-separated floats")
        return 1

    if not (-90 <= bbox[0] < bbox[2] <= 90 and -180 <= bbox[1] < bbox[3] <= 180):
        parser.error("Bounding box must be south,west,north,east within valid coordinate ranges")
    if args.limit <= 0 or args.delay < 0:
        parser.error("Limit must be positive and delay cannot be negative")
    restaurants = fetch_osm_restaurants(bbox, args.limit)
    if not restaurants:
        print("No restaurants found")
        return 1

    print(f"Enriching {len(restaurants)} restaurants with Google Maps...")
    enriched = enrich_restaurants(restaurants, args.api_key, args.delay) if args.api_key else restaurants

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(enriched, f, indent=2, ensure_ascii=False)

    print(f"Saved {len(enriched)} restaurants to {output_path}")
    return 0


if __name__ == "__main__":
    exit(main())