"""Read-only assertions against the seeded starter catalogs on a real Typesense server."""
from core.contracts import Person, SearchRequest, validate_response
from core.services import AppServices, Settings
from categories import eat, do, watch, play


def main():
    services = AppServices(Settings.from_env())
    assert services.health(), "Typesense is not healthy"
    cases = [
        (eat, SearchRequest('eat', (), query='mexcan', filters={'budget':25}), {'mesa','market'}),
        (eat, SearchRequest('eat', (Person('p','P',avoids=('Italian',)),), filters={'budget':20}), {'mesa','corner'}),
        (eat, SearchRequest('eat', (), filters={'budget':30,'dietary_options':['Vegetarian','Vegan']}), {'mesa','saffron','market'}),
        (do, SearchRequest('do', (), filters={'budget':0,'max_duration':50,'setting':'Outdoors'}), {'picnic','walk'}),
        (watch, SearchRequest('watch', (), query='adventur', filters={'max_duration':110}), {'detour','cloud'}),
        (play, SearchRequest('play', (), filters={'players':8,'max_duration':30}), {'draw','word','tower'}),
        (eat, SearchRequest('eat', (), filters={'budget':0}), set()),
    ]
    for module, request, expected in cases:
        response=module.search(request,services)
        validate_response(response,request)
        assert response.engine=='Typesense'
        actual={c.id for c in response.candidates}
        assert actual==expected, (request.category_id,actual,expected)
        print(f'{request.category_id}: {len(actual)} expected matches — real Typesense passed')
    print('All 7 live search checks passed.')


if __name__=='__main__':
    main()
