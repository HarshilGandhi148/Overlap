"""Explicit source ingestion; no network calls happen at import time."""
import json
import math
import os
import re
import time
from collections import defaultdict, deque
from dataclasses import replace
from pathlib import Path
import requests
from nearby.models import Activity, AreaBatch, AppError, CATEGORIES, MAX_PLACES, distance_miles

ROOT = Path(__file__).resolve().parents[1]
TTL_SECONDS = 1800
SELECTORS = {
    'leisure': 'park|garden|playground|sports_centre|miniature_golf|bowling_alley|escape_game',
    'tourism': 'museum|gallery|attraction|zoo|aquarium',
    'amenity': 'cinema|theatre|arts_centre|cafe|restaurant',
}


def fetch_elements(location):
    selectors = ''.join(f'nwr(around:16093.44,{location.latitude},{location.longitude})[name]["{key}"~"^({value})$"];' for key, value in SELECTORS.items())
    lat_delta = 16093.44 / 111195
    lon_delta = lat_delta / max(.01, math.cos(math.radians(location.latitude)))
    bounds = f'{max(-90,location.latitude-lat_delta)},{max(-180,location.longitude-lon_delta)},{min(90,location.latitude+lat_delta)},{min(180,location.longitude+lon_delta)}'
    query = f'[out:json][timeout:60][bbox:{bounds}];({selectors});out center tags;'
    endpoint = os.getenv('OVERPASS_URL', 'https://overpass-api.de/api/interpreter')
    try:
        response = requests.post(endpoint, data={'data': query}, headers={'User-Agent': 'OverlapHackathonDemo/1.0'}, timeout=(10, 75))
        response.raise_for_status()
        payload = response.json()
        if payload.get('remark') or not isinstance(payload.get('elements'), list):
            raise AppError('The places service returned an incomplete area. Retry later; partial coverage was not accepted.')
        return payload['elements']
    except (requests.RequestException, ValueError) as exc:
        raise AppError('The places service is unavailable or busy. Retry later, or keep the previously loaded area.') from exc


def category_tags(tags):
    result = []
    for key, mapping in {
        'leisure': {'park':'park', 'garden':'park', 'playground':'playground', 'sports_centre':'sports', 'miniature_golf':'entertainment', 'bowling_alley':'entertainment', 'escape_game':'entertainment'},
        'tourism': {'museum':'museum','gallery':'gallery','attraction':'attraction','zoo':'attraction','aquarium':'attraction'},
        'amenity': {'cinema':'entertainment','theatre':'entertainment','arts_centre':'gallery','cafe':'cafe','restaurant':'restaurant'},
    }.items():
        if tags.get(key) in mapping: result.append(mapping[tags[key]])
    return sorted(set(result))


def normalize(elements, now=None):
    found = {}
    for element in elements:
        if not isinstance(element, dict) or 'id' not in element:
            continue
        tags = element.get('tags', {})
        if not isinstance(tags, dict):
            continue
        categories = category_tags(tags)
        name = str(tags.get('name', '')).strip()
        if not name or not categories or element.get('type') not in ('node','way','relation'): continue
        position = element if element['type'] == 'node' else element.get('center', {})
        if not isinstance(position, dict):
            continue
        if 'lat' not in position or 'lon' not in position: continue
        try:
            lat, lon = float(position['lat']), float(position['lon'])
        except (TypeError, ValueError):
            continue
        if not -90 <= lat <= 90 or not -180 <= lon <= 180: continue
        ident = f"{element['type']}:{element['id']}"
        activity = Activity(id=ident, name=name, location=[lat,lon], categories=categories,
            description=tags.get('description:en', tags.get('description','')),
            tags=[str(tags[k]).replace('_',' ') for k in ('leisure','tourism','amenity','sport','cuisine') if k in tags],
            address=' '.join(tags.get(k,'') for k in ('addr:housenumber','addr:street','addr:city','addr:postcode')).strip(),
            website=tags.get('website',tags.get('contact:website','')), opening_hours=tags.get('opening_hours',''),
            wheelchair=tags.get('wheelchair','unknown'), fee=tags.get('fee','unknown'),
            source_url=f"https://www.openstreetmap.org/{element['type']}/{element['id']}", fetched_at=int(now or time.time()))
        # Only unconditional, unambiguous admission charges can become numeric data.
        if tags.get('fee') == 'no' and not tags.get('fee:conditional') and not tags.get('charge:conditional'):
            activity.cost_min = activity.cost_max = 0
            activity.cost_basis = 'published OSM tag'
        elif not tags.get('charge:conditional') and re.fullmatch(r'\d+(?:\.\d+)? USD(?:/person)?', tags.get('charge','')):
            activity.cost_min = activity.cost_max = float(tags['charge'].split()[0])
            activity.cost_basis = 'published OSM tag'
        if activity.cost_max is not None:
            activity.metadata_sources = [activity.source_url]
        found[ident] = activity
    groups = defaultdict(list)
    result = []
    for a in sorted(found.values(), key=lambda a: a.id):
        key = ' '.join(re.findall(r'\w+', a.name.casefold()))
        duplicate = next((b for b in groups[key] if set(a.categories)&set(b.categories) and distance_miles(a.location,b.location)*1609.344 <= 30), None)
        if duplicate:
            duplicate.aliases.append(a.id)
            duplicate.categories = sorted(set(duplicate.categories+a.categories))
            duplicate.tags = sorted(set(duplicate.tags+a.tags))
        else:
            result.append(a); groups[key].append(a)
    return result


def enrich_places(places, path=None):
    path = path or ROOT/'data'/'nyc_enrichment.json'
    if not path.exists(): return places
    try:
        metadata = json.loads(path.read_text())['places']
        if not isinstance(metadata, dict):
            raise ValueError('Expected a metadata mapping')
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise AppError('Could not read the activity enrichment file. Check its JSON and places mapping.') from exc
    allowed = {'description','cost_min','cost_max','duration_min','duration_max','cost_basis','duration_basis','metadata_sources','verified_at','activity_scope'}
    enriched = []
    for a in places:
        entry = next((metadata[k] for k in [a.id]+a.aliases if k in metadata), None)
        if not entry:
            enriched.append(a); continue
        try:
            for low, high in [('cost_min','cost_max'),('duration_min','duration_max')]:
                if not math.isfinite(entry[low]) or not math.isfinite(entry[high]) or not 0 <= entry[low] <= entry[high]:
                    raise ValueError('Invalid range')
            if entry['duration_min'] <= 0 or entry.get('currency') != 'USD' or not entry.get('metadata_sources'):
                raise ValueError('Missing metadata')
        except (KeyError, TypeError, ValueError) as exc:
            raise AppError('The enrichment file needs finite cost/duration ranges, USD costs, and sources.') from exc
        enriched.append(replace(a, **{k:v for k,v in entry.items() if k in allowed}))
    return enriched


def balanced_cap(places, location, limit=MAX_PLACES):
    if len(places) <= limit: return places
    buckets = {category:deque() for category in CATEGORIES}
    for a in sorted(places, key=lambda a: (distance_miles(location.key,a.location),a.id)):
        # Enriched places participate normally; enrichment does not change retrieval priority.
        buckets[a.categories[0]].append(a)
    result=[]
    while len(result)<limit and any(buckets.values()):
        for bucket in buckets.values():
            if bucket and len(result)<limit: result.append(bucket.popleft())
    return result


def load_area(location, previous=None, force=False, fetcher=None, now=None):
    now = time.time() if now is None else now
    if previous and previous.location_key == location.key and not force and now-previous.loaded_at < TTL_SECONDS:
        return previous
    start=time.perf_counter()
    try:
        if fetcher is None:
            from nearby.google_places import fetch_google_activities
            places = fetch_google_activities(location)
        else:
            places=enrich_places(normalize(fetcher(location), now=now))
        capped=balanced_cap(places,location)
        return AreaBatch(location.key,capped,now,len(places),len(capped)<len(places),load_seconds=time.perf_counter()-start)
    except AppError:
        if previous and previous.location_key == location.key:
            return replace(previous, stale=True, warning='Refresh failed. Showing the previously loaded area; its data may be stale.')
        raise
