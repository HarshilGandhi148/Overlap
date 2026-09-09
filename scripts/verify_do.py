"""Quick read-only check: seed Do first, then run python -m scripts.verify_do."""
import json
from core.contracts import Person, SearchRequest, validate_response
from core.services import AppServices, Settings
from nearby.adapter import service_for
from nearby.models import NYC, distance_miles
from categories import do


def main():
    services = AppServices(Settings.from_env())
    request = SearchRequest('do', (Person('alex', 'Alex'), Person('sam', 'Sam')), filters={
        'do_source': 'snapshot', 'radius_miles': 5,
        'do_people': {
            'alex': {'opinion': 'A relaxing stroll among trees and flowers', 'max_minutes': 60, 'max_cost': 0},
            'sam': {'opinion': 'An outdoor place to sit, talk, and take photographs', 'max_minutes': 90, 'max_cost': 20},
        },
    })
    result = do.search(request, services)
    validate_response(result, request)
    assert result.engine == 'Typesense' and result.candidates, 'Expected real semantic search results'
    service = service_for(services)
    for candidate in result.candidates:
        doc = service.client.collections[service.collection].documents[candidate.id].retrieve()
        # Cost and duration no longer constrain the shared Do flow.
        assert distance_miles(NYC.key, doc['location']) <= 5.01
    print(json.dumps({'engine': result.engine, 'collection': service.collection,
                      'eligible': result.total_found, 'returned': len(result.candidates),
                      'top_activity': result.candidates[0].title,
                      'confirmed': 'Semantic group search with a 5-mile radius and no cost/duration/access filters',
                      'details': result.warnings[1]}, indent=2))


if __name__ == '__main__':
    main()
