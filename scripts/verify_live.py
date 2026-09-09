"""Read-only checks of the real Eat index: python -m scripts.verify_live."""
from categories import eat
from core.contracts import SearchRequest, Person, validate_response
from core.services import AppServices, Settings


def main():
    services=AppServices(Settings.from_env())
    docs=eat.load_restaurants()
    first=docs[0]
    coords=first['location']
    request=SearchRequest('eat',(),filters={'meeting_point':f"{coords['lat']},{coords['lng']}",'max_distance':1,'use_budget':False})
    result=eat.search(request,services)
    validate_response(result,request)
    assert result.engine=='Typesense' and result.candidates
    indexed=services.client.collections[services.collection_name('eat_restaurants')]
    for candidate in result.candidates:
        doc=indexed.documents[candidate.id].retrieve()
        assert eat.haversine_km(coords['lat'],coords['lng'],*doc['location']) <= 1.01
    typo=eat.search(SearchRequest('eat',(),query='Litle Alley'),services)
    assert any(c.title=='Little Alley' for c in typo.candidates), 'Typo search failed'
    empty=eat.search(SearchRequest('eat',(),query='nonsensezzzzxyz'),services)
    assert not empty.candidates
    budget=eat.search(SearchRequest('eat',(Person('p','P',avoids=('Italian',)),),filters={'budget':40}),services)
    for candidate in budget.candidates:
        doc=indexed.documents[candidate.id].retrieve()
        assert doc['budget_estimate']<=40 and 'Italian' not in doc['cuisine']
    vegan=eat.search(SearchRequest('eat',(),filters={'dietary_options':['Vegan']}),services)
    for candidate in vegan.candidates:
        assert 'Vegan' in indexed.documents[candidate.id].retrieve()['dietary_options']
    print(f"PASS Typesense: {indexed.retrieve()['num_documents']} restaurants; geo={len(result.candidates)}, typo={len(typo.candidates)}, budget/exclusions={len(budget.candidates)}, dietary={len(vegan.candidates)}, irrelevant query=0")


if __name__=='__main__': main()
