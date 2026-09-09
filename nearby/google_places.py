"""Bounded Google Places (New) ingestion for explicit Do area loads."""
import os
import time
import requests
from nearby.models import Activity, AppError

TYPE_MAP = {'park':'park', 'museum':'museum', 'art_gallery':'gallery',
            'tourist_attraction':'attraction', 'zoo':'attraction', 'aquarium':'attraction',
            'playground':'playground', 'movie_theater':'entertainment',
            'bowling_alley':'entertainment', 'sports_complex':'sports'}


def fetch_google_activities(location):
    key = os.getenv('GOOGLE_MAPS_API_KEY', '')
    if not key:
        raise AppError('Configure GOOGLE_MAPS_API_KEY in .env to load Google Places.')
    try:
        response = requests.post('https://places.googleapis.com/v1/places:searchNearby',
            headers={'X-Goog-Api-Key':key, 'X-Goog-FieldMask':'places.id,places.displayName,places.location,places.types,places.formattedAddress,places.googleMapsUri'},
            json={'includedTypes':list(TYPE_MAP), 'maxResultCount':20, 'rankPreference':'DISTANCE',
                  'locationRestriction':{'circle':{'center':{'latitude':location.latitude,'longitude':location.longitude},'radius':16093.44}}}, timeout=20)
        response.raise_for_status()
        places = response.json().get('places', [])
    except (requests.RequestException, ValueError) as exc:
        raise AppError('Google Places could not load this area. Check the Places API (New) key, quota and billing, then retry.') from exc
    result=[]
    for place in places:
        position=place.get('location', {})
        categories=sorted({TYPE_MAP[t] for t in place.get('types', []) if t in TYPE_MAP})
        if not place.get('id') or not categories or not place.get('displayName',{}).get('text'):
            continue
        if 'latitude' not in position or 'longitude' not in position:
            continue
        result.append(Activity(id='google:'+place['id'], name=place['displayName']['text'],
            location=[position['latitude'],position['longitude']], categories=categories,
            description=', '.join(t.replace('_',' ') for t in place.get('types',[])),
            tags=categories, address=place.get('formattedAddress',''),
            source_url=place.get('googleMapsUri',''), fetched_at=int(time.time())))
    # Google does not supply reliable admission prices or visit lengths.
    # Do now ranks without those fields; unknown metadata does not block results.
    return result
