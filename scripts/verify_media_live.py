"""Explicit checks against the configured, imported Watch/Play Typesense catalogs."""
from dataclasses import replace
from categories import watch, play
from core.contracts import Person, SearchRequest, validate_response
from core.services import AppServices, Settings
from core.storage import Store


def main():
    services = AppServices(Settings.from_env())
    assert services.health(), "Typesense is not healthy"
    store = Store()
    movies, games = store.catalog("watch"), store.catalog("play")
    assert movies and games, "Import Watch and Play catalogs before verification"
    assert all(r["source"] == "OMDb" for r in movies)
    assert all(r["source"] == "IGDB" for r in games)
    person = Person("test-person", "Test participant", avoids=("Horror",), requirements={"max_duration": 100})
    request = SearchRequest("watch", (person,))
    result = watch.search(request, services)
    validate_response(result, request)
    assert result.engine == "Typesense" and result.candidates
    by_id = {r["id"]: r for r in movies}
    assert all(by_id[c.id]["duration"] <= 100 and "Horror" not in c.tags for c in result.candidates)
    impossible = watch.search(replace(request, filters={"max_duration": 1}), services)
    assert not impossible.candidates and impossible.conflicts
    assert watch._provider.lookup("Toy Stroy", services), "Movie typo lookup failed"
    typed = watch.search(SearchRequest('watch', (), query='Toy Stroy'), services)
    assert {c.title for c in typed.candidates} == {'Toy Story', 'Toy Story 3'}, 'A typed query returned unrelated movies'
    assert not watch.search(SearchRequest('watch', (), query='zzzxxyynonexistenttitle'), services).candidates
    request = SearchRequest("play", (), filters={"players": 4, "play_mode": "Local", "platform": "PC (Microsoft Windows)", "max_duration": 0})
    result = play.search(request, services)
    validate_response(result, request)
    assert result.engine == "Typesense" and result.candidates
    by_id = {r["id"]: r for r in games}
    assert all(any(c["mode"] == "Local" and c["platform"] == "PC (Microsoft Windows)" and c["max_players"] >= 4
                   for c in by_id[item.id]["multiplayer"]) for item in result.candidates)
    timed = play.search(replace(request, filters={**request.filters, "max_duration": 90}), services)
    assert timed.unresolved, "Missing game time should be visible as unresolved"
    assert play._provider.lookup("Overcooked", services), "Game title lookup failed"
    print(f"PASS: {len(movies)} OMDb movies and {len(games)} IGDB games in primary storage.")
    print("PASS: real Typesense searches, runtime/exclusions, player/platform pairing, typo lookup, conflicts and missing-time handling.")


if __name__ == "__main__":
    main()
