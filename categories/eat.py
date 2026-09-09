"""Eat category: NYC restaurants from OSM + Google Maps Places API (New)."""
import json
import math
import re
import os
from functools import lru_cache
from core.catalog import CatalogProvider, quote
from pathlib import Path
from typing import Any

from core.contracts import (
    Candidate,
    CategorySearchError,
    CategorySpec,
    FilterField,
    Person,
    SearchRequest,
    SearchResponse,
    SeedReport,
)
from core.services import AppServices, ROOT

DATA_FILE = ROOT / "data" / "eat_real.json"
FALLBACK_FILE = ROOT / "data" / "eat.json"

CUISINE_OPTIONS = (
    "Pizza", "Italian", "Chinese", "Japanese", "Mexican", "Indian",
    "American", "Thai", "Korean", "Vietnamese", "Mediterranean",
    "French", "Seafood", "Steakhouse", "BBQ", "Cafe", "Bakery",
    "Deli", "Sandwich", "Bagel", "Donut", "Ice Cream", "Dessert",
)

DIETARY_OPTIONS = ("Vegetarian", "Vegan", "Gluten-free", "Halal", "Kosher")


def load_restaurants() -> list[dict]:
    path = DATA_FILE
    try:
        data = json.loads(path.read_text())
        if not isinstance(data, list):
            raise ValueError("Expected a list")
        records = [normalize_restaurant(r) for r in data]
        if any(not r.get('id') or not r.get('title') for r in records) or len({r['id'] for r in records}) != len(records):
            raise ValueError('Missing or duplicate IDs')
        return records
    except (OSError, ValueError, TypeError) as exc:
        raise CategorySearchError(f"Could not load {path.name}. Run python -m scripts.import_eat, then python -m scripts.seed eat.") from exc


def normalize_restaurant(r: dict) -> dict:
    """Normalize old (eat.json) and new (eat_real.json) formats to common schema."""
    out = dict(r)
    if "tags" in r and "cuisine" not in r:
        out["cuisine"] = r["tags"]
    if "cost" in r and "budget_estimate" not in r:
        out["budget_estimate"] = r["cost"]
        out["price_range"] = "$" if r["cost"] < 20 else "$$" if r["cost"] < 40 else "$$$"
        out["price_level"] = 1 if r["cost"] < 20 else 2 if r["cost"] < 40 else 3
    if "location" in r and isinstance(r["location"], dict):
        out["location"] = {"lat": r["location"].get("lat", 0), "lng": r["location"].get("lng", 0)}
    if "provenance" not in r:
        out["provenance"] = {"source": "sample", "enriched_by": None}
    return out


@lru_cache(maxsize=128)
def geocode_address(address: str, api_key: str) -> tuple[float, float] | None:
    import requests
    try:
        response = requests.post('https://places.googleapis.com/v1/places:searchText',
            headers={'X-Goog-Api-Key': api_key, 'X-Goog-FieldMask': 'places.location'},
            json={'textQuery': address, 'pageSize': 1}, timeout=10)
        response.raise_for_status()
        places = response.json().get('places', [])
        if places:
            loc = places[0]['location']
            return loc['latitude'], loc['longitude']
    except (requests.RequestException, ValueError, KeyError, TypeError):
        pass
    return None


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * R * math.asin(math.sqrt(min(1, max(0, a))))


def eligible(restaurant: dict, request: SearchRequest) -> tuple[bool, list[str]]:
    """Check hard constraints. Returns (is_eligible, warnings)."""
    filters = request.filters
    warnings = []

    budget = filters.get("budget") if filters.get("use_budget", True) else None
    if budget is not None:
        est = restaurant.get("budget_estimate")
        if est is None:
            warnings.append("Price unknown — cannot verify budget")
            return False, warnings
        if est > budget:
            return False, warnings

    dietary_req = filters.get("dietary_options", [])
    if dietary_req:
        available = set(restaurant.get("dietary_options", []))
        missing = [d for d in dietary_req if d not in available]
        if missing:
            return False, warnings

    avoids = {v for p in request.people for v in p.avoids}
    if avoids & set(restaurant.get("cuisine", [])):
        return False, warnings

    return True, warnings


def to_candidate(restaurant: dict, request: SearchRequest, distance_km: float | None = None) -> Candidate:
    cuisine = restaurant.get("cuisine", [])
    tags = tuple(cuisine)
    matched_likes = {p.id: tuple(v for v in p.likes if v in cuisine) for p in request.people}

    facts = {"Address": restaurant.get("address", ""), "Source": "Google Maps / OpenStreetMap" if "google" in str(restaurant.get("provenance", "")) and "google_maps" in str(restaurant.get("provenance", "")) else "OpenStreetMap"}
    if restaurant.get("price_range"):
        facts["Price basis"] = "Rough estimate from Google price tier; check the menu."
        facts["Price"] = restaurant["price_range"]
        if restaurant.get("budget_estimate") is not None:
            facts["Est. Cost"] = f"${restaurant['budget_estimate']} / person"
    if restaurant.get("rating"):
        facts["Rating"] = f"{restaurant['rating']:.1f} ★"
    if distance_km is not None:
        facts["Distance"] = f"{distance_km:.1f} km"
    if restaurant.get("dietary_options"):
        facts["Dietary"] = ", ".join(restaurant["dietary_options"])

    reasons = []
    if distance_km is not None:
        reasons.append(f"Within {distance_km:.1f} km of meeting point")
    budget = request.filters.get("budget") if request.filters.get("use_budget", True) else None
    if budget is not None and restaurant.get("budget_estimate") is not None and restaurant["budget_estimate"] <= budget:
        reasons.append(f"Estimated cost within ${budget}/person")
    if matched_likes:
        total_matches = sum(len(v) for v in matched_likes.values())
        if total_matches:
            reasons.append(f"Matches {total_matches} cuisine preference(s)")

    return Candidate(
        category_id=request.category_id,
        id=restaurant["id"],
        title=restaurant["title"],
        description=restaurant.get("description", ""),
        facts=facts,
        tags=tags,
        matched_likes=matched_likes,
        reasons=tuple(reasons) or ("Fits the selected group constraints.",),
        source_url=restaurant.get("source_url"),
        image_url=None,
    )


def filter_expression(request: SearchRequest) -> str:
    parts = []
    filters = request.filters

    if filters.get("budget") is not None and filters.get("use_budget", True):
        parts.append(f"budget_estimate:<={float(filters['budget'])}")
    for opt in filters.get("dietary_options", []):
        parts.append(f"dietary_options:={quote(opt)}")
    avoids = sorted({v for p in request.people for v in p.avoids})
    if avoids:
        parts.append("cuisine:!=[" + ",".join(quote(v) for v in avoids) + "]")
    return " && ".join(parts)


def search_typesense(request: SearchRequest, services: AppServices, meeting_coords: tuple[float, float] | None) -> SearchResponse:
    try:
        coll_name = services.collection_name("eat_restaurants")
        params = {
            "q": request.query.strip() or "*",
            "query_by": "title,description,cuisine",
            "per_page": min(request.limit, 250),
            "num_typos": 2,
            "drop_tokens_threshold": 0,
            "prefix": True,
            "filter_by": filter_expression(request),
        }
        if meeting_coords:
            radius = request.filters.get("max_distance", 5)
            params["filter_by"] = " && ".join(filter(None, [params["filter_by"], f"location:({meeting_coords[0]}, {meeting_coords[1]}, {radius} km)"]))
            params["sort_by"] = f"location({meeting_coords[0]}, {meeting_coords[1]}):asc"

        result = services.client.collections[coll_name].documents.search(params)
        hits = result.get("hits", [])
        candidates = []
        for h in hits:
            doc = h["document"]
            is_eligible, _ = eligible(doc, request)
            if is_eligible:
                distance = None
                if meeting_coords and doc.get("location"):
                    distance = haversine_km(
                        meeting_coords[0], meeting_coords[1],
                        doc["location"][0], doc["location"][1]
                    )
                candidates.append(to_candidate(doc, request, distance))

        return SearchResponse(
            tuple(candidates),
            result.get("found"),
            ("NYC restaurant snapshot · © OpenStreetMap contributors (ODbL); enriched records: Google Maps. Prices are estimates; missing prices are excluded when the budget filter is enabled.",),
            "Typesense",
            result.get("search_time_ms"),
        )
    except CategorySearchError:
        raise
    except Exception as exc:
        from typesense.exceptions import ObjectNotFound, RequestUnauthorized
        if isinstance(exc, ObjectNotFound):
            raise CategorySearchError("Eat catalog not indexed. Run: python -m scripts.seed eat") from exc
        if isinstance(exc, RequestUnauthorized):
            raise CategorySearchError("Typesense rejected API key. Check .env.") from exc
        raise CategorySearchError("Typesense search unavailable. Check server and Developer settings.") from exc


SPEC = CategorySpec(
    "eat", "Eat", "Where should we eat?", "Find a restaurant the whole group can get behind.",
    filter_fields=(
        FilterField("meeting_point", "Meeting point (address or landmark)", "text", "",
                    help="Optional. Enter an address or latitude, longitude. Blank searches the whole NYC snapshot."),
        FilterField("max_distance", "Max distance (km)", "number", 3, minimum=1, maximum=20, step=1),
        FilterField("use_budget", "Filter by estimated cost", "checkbox", False),
        FilterField("budget", "Estimated budget per person ($)", "number", 40, minimum=0, maximum=200),
        FilterField("dietary_options", "Required dietary options", "multiselect", [],
                    DIETARY_OPTIONS,
                    help="Based on OSM tags; not verified for allergen safety."),
    ),
    like_options=CUISINE_OPTIONS,
    avoid_options=CUISINE_OPTIONS,
    is_sample=False,
    custom=False,
)


def get_spec() -> CategorySpec:
    return SPEC


def meeting_coordinates(text: str) -> tuple[float, float] | None:
    text = text.strip()
    if not text:
        return None
    if re.fullmatch(r"[+\-\d.]+\s*,\s*[+\-\d.]+", text):
        try:
            lat, lon = map(float, text.split(','))
            if -90 <= lat <= 90 and -180 <= lon <= 180:
                return lat, lon
        except ValueError:
            pass
        raise CategorySearchError("Enter valid latitude, longitude coordinates.")
    key = os.getenv('GOOGLE_MAPS_API_KEY', '')
    coords = geocode_address(text, key) if key else None
    if coords is None:
        raise CategorySearchError("Could not locate that meeting point. Try latitude, longitude or check GOOGLE_MAPS_API_KEY in .env. Distance has not been ignored.")
    return coords


def search(request: SearchRequest, services: AppServices) -> SearchResponse:
    if request.custom_options:
        raise CategorySearchError("Search restaurant names in the catalog so your filters can be checked.")
    if services.mode == 'sample':
        if request.filters.get('meeting_point', '').strip():
            raise CategorySearchError("Fictional sample restaurants have no real locations. Clear the meeting point or use Typesense mode.")
        from dataclasses import replace
        filters = dict(request.filters)
        if not filters.get('use_budget', True):
            filters.pop('budget', None)
        return CatalogProvider(SPEC).search(replace(request, filters=filters), services)
    return search_typesense(request, services, meeting_coordinates(request.filters.get('meeting_point', '')))


def seed(services: AppServices) -> SeedReport:
    from typesense.exceptions import ObjectAlreadyExists

    name = services.collection_name("eat_restaurants")
    fields = [
        {"name": "title", "type": "string"},
        {"name": "description", "type": "string"},
        {"name": "cuisine", "type": "string[]", "facet": True},
        {"name": "dietary_options", "type": "string[]", "facet": True},
        {"name": "price_level", "type": "int32", "optional": True, "facet": True},
        {"name": "budget_estimate", "type": "float", "optional": True},
        {"name": "rating", "type": "float", "optional": True},
        {"name": "location", "type": "geopoint"},
        {"name": "address", "type": "string"},
        {"name": "source_url", "type": "string", "optional": True},
        {"name": "website_url", "type": "string", "optional": True},
        {"name": "google_place_id", "type": "string", "optional": True},
        {"name": "provenance", "type": "string"},
    ]
    try:
        services.client.collections.create({"name": name, "fields": fields})
    except ObjectAlreadyExists:
        pass

    restaurants = load_restaurants()
    if not restaurants:
        return SeedReport(SPEC.id, 0)

    for r in restaurants:
        for key in list(r):
            if r[key] is None:
                del r[key]
        r.setdefault("description", r["title"] + " — " + r.get("address", ""))
        r.setdefault("cuisine", [])
        r.setdefault("dietary_options", [])
        if isinstance(r.get("location"), dict):
            r["location"] = [r["location"]["lat"], r["location"]["lng"]]
        r["provenance"] = json.dumps(r.get("provenance", {}))

    report = services.client.collections[name].documents.import_(restaurants, {"action": "upsert"})
    if isinstance(report, str):
        report = [json.loads(line) for line in report.splitlines() if line.strip()]
    errors = tuple(str(r.get("error", "Import failed")) for r in report if not r.get("success"))
    return SeedReport(SPEC.id, sum(bool(r.get("success")) for r in report), len(errors), errors)