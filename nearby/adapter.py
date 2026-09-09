"""Translate nearby retrieval into the existing SearchRequest/Candidate interface."""
import json
from pathlib import Path
from core.contracts import Candidate, CategorySearchError, SearchResponse, SeedReport
from nearby.ingestion import enrich_places, normalize
from nearby.models import NYC, AppError, LocationContext, OutingRequest, ParticipantPreferences
from nearby.search import SearchService

ROOT = Path(__file__).resolve().parents[1]


def snapshot_places():
    try:
        payload = json.loads((ROOT / 'data/nyc_places.json').read_text())
        return enrich_places(normalize(payload['elements']))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise AppError('Could not load the saved NYC places. Check data/nyc_places.json and nyc_enrichment.json.') from exc


def service_for(services):
    if services.mode != 'typesense':
        raise CategorySearchError('Do needs real Typesense for semantic search. Choose Typesense in Settings.')
    # A dedicated collection keeps the old fixture index and other teammates' data untouched.
    # The longer client timeout permits the initial automatic model download.
    return SearchService(settings=services.settings,
                         collection=services.collection_name('do') + '_nearby_v1')


def outing_from_request(request):
    f = request.filters
    profiles = f.get('do_people', {})
    people = []
    for person in request.people:
        profile = profiles.get(person.id, {})
        if not str(profile.get('opinion', '')).strip():
            raise CategorySearchError(f'Save activity preferences for {person.name} before searching.')
        people.append(ParticipantPreferences(
            person.id, person.name, profile['opinion'], exclusions=tuple(profile.get('exclusions', ())),
        ))
    source = f.get('do_source', 'snapshot')
    location = NYC if source == 'snapshot' else LocationContext(
        float(f['latitude']), float(f['longitude']), 'manual')
    return OutingRequest(location, float(f.get('radius_miles', 5)), tuple(people), enforce_metadata_limits=False)


def as_candidate(item, request):
    doc = item.document
    facts = {
        'Match': f'{item.score:.1f} / 100 group match',
        'Distance': f'{item.distance_miles:.1f} mi away',
    }
    reasons = [f'{p.name}: {100 * item.individual_scores[p.id]:.1f} / 100 semantic match to their written preferences.'
               for p in request.people]
    reasons += ['Typesense checked your radius and category exclusions.',
                'Group match combines everyone’s written preferences with distance.']
    return Candidate('do', doc['id'], doc['name'], doc.get('description', ''), facts,
                     tuple(doc.get('categories', ())), {}, tuple(reasons), doc.get('source_url'))


def search(request, services):
    try:
        service = service_for(services)
        outing = outing_from_request(request)
        if request.filters.get('do_source', 'snapshot') == 'snapshot':
            ids = [a.id for a in snapshot_places()]
            source = 'Saved NYC OpenStreetMap snapshot · 50 real places captured 2026-09-08; not live listings.'
        else:
            ids = request.filters.get('candidate_ids', [])
            if not ids:
                raise CategorySearchError('Load nearby places for this location before searching.')
            source = request.filters.get('area_note', 'Google Maps · nearby selection')
        result = service.recommend(outing, ids)
        warnings = [source,
                    f'Typesense: {result.eligible_count} eligible / {result.geographic_count} inside your radius · '
                    f'{result.query_seconds:.2f}s total search.',
                    ('Place data © OpenStreetMap contributors · ODbL. ' if request.filters.get('do_source', 'snapshot') == 'snapshot' else 'Place data: Google Maps. Ranked by group preferences and distance.')]
        items = result.nearest if request.filters.get('order') == 'Nearest first' else result.ranked
        return SearchResponse(tuple(as_candidate(item, request) for item in items[:min(request.limit, 10)]),
                              result.eligible_count, tuple(warnings), 'Typesense')
    except CategorySearchError:
        raise
    except (AppError, ValueError, KeyError, TypeError) as exc:
        if isinstance(exc, AppError):
            raise CategorySearchError(str(exc)) from exc
        raise CategorySearchError('Check the saved activity preferences, limits, and location, then retry.') from exc


def seed(services):
    try:
        ids, failed = service_for(services).index_places(snapshot_places())
        return SeedReport('do', len(ids), failed, ('Some NYC places failed to index. Check Typesense and retry.',) if failed else ())
    except AppError as exc:
        raise CategorySearchError(str(exc)) from exc
