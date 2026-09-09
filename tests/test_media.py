import json
import tempfile
from dataclasses import replace
from pathlib import Path
import unittest
from unittest.mock import Mock, patch
from categories import watch, play
from core.contracts import Candidate, CategorySearchError, Person, SearchRequest
from core.media_apis import IGDB, normalize_movie, normalize_game, request_json, AuthenticationError
from core.media_matching import evaluate, match_records
from core.services import AppServices, Settings
from core.state import CategoryState, GroupState
from core.storage import Store


class MatchingTests(unittest.TestCase):
    def movie(self):
        return {"id": "movie", "title": "Movie", "tags": ["Comedy"], "duration": 95, "source": "OMDb"}

    def game(self):
        return {"id": "game", "title": "Game", "tags": ["Cooperative"], "format": "Video", "source": "IGDB",
                "multiplayer": [{"platform": "PC", "mode": "Local", "max_players": 4},
                                {"platform": "Console", "mode": "Online", "max_players": 8}],
                "curated": {"session_max": 20, "setup_minutes": 5, "teaching_minutes": 10,
                            "equipment": [], "controllers_per_player": 1, "source": "Demo assessment"}}

    def test_personal_requirements_and_anything(self):
        req = SearchRequest("watch", (Person("p", "Pat", requirements={"max_duration": 90, "anything": True}),))
        self.assertEqual(evaluate(self.movie(), req)[0].eligibility, "excluded")

    def test_missing_runtime_and_genres_are_unresolved(self):
        movie = self.movie(); movie.pop("duration"); movie["tags"] = []
        req = SearchRequest("watch", (Person("p", "Pat", avoids=("Horror",)),), filters={"max_duration": 100})
        candidate, _ = evaluate(movie, req)
        self.assertEqual(candidate.eligibility, "unresolved")
        self.assertEqual(len(candidate.unknowns), 2)

    def test_watched_titles_case_insensitive(self):
        req = SearchRequest("watch", (Person("p", "Pat", requirements={"watched": ["MOVIE"]}),))
        self.assertEqual(evaluate(self.movie(), req)[0].eligibility, "excluded")

    def test_platform_and_mode_capacity_cannot_be_combined(self):
        req = SearchRequest("play", (), filters={"platform": "PC", "play_mode": "Local", "players": 8})
        self.assertEqual(evaluate(self.game(), req)[0].eligibility, "excluded")
        req = replace(req, filters={"platform": "PC", "play_mode": "Online", "players": 4})
        self.assertEqual(evaluate(self.game(), req)[0].eligibility, "unresolved")

    def test_teaching_and_setup_count(self):
        req = SearchRequest("play", (), filters={"players": 4, "max_duration": 30})
        self.assertEqual(evaluate(self.game(), req)[0].eligibility, "excluded")
        game = self.game(); game["curated"].pop("teaching_minutes")
        self.assertEqual(evaluate(game, req)[0].eligibility, "unresolved")

    def test_online_requires_each_member_access_and_common_platform(self):
        people = (Person("a", "A", access={"platforms": ["Console"], "owned": ["Game"]}),
                  Person("b", "B", access={"platforms": ["PC"], "owned": []}))
        req = SearchRequest("play", people, filters={"players": 4, "play_mode": "Online", "check_access": True})
        result = evaluate(self.game(), req)[0]
        self.assertEqual(result.eligibility, "unresolved")
        self.assertTrue(any("B: game ownership" in s for s in result.unknowns))

    def test_local_shares_host_and_controllers(self):
        people = (Person("a", "A", access={"platforms": ["PC"], "owned": ["Game"], "controllers": 2}),
                  Person("b", "B", access={"controllers": 2}))
        req = SearchRequest("play", people, filters={"players": 4, "check_access": True})
        self.assertEqual(evaluate(self.game(), req)[0].eligibility, "verified")

    def test_manual_needs_confirmation_and_same_constraints(self):
        movie = {**self.movie(), "source": "Participant-provided"}
        req = SearchRequest("watch", (), filters={"max_duration": 100})
        self.assertEqual(evaluate(movie, req)[0].eligibility, "unresolved")
        movie["confirmed_details"] = True
        self.assertEqual(evaluate(movie, req)[0].eligibility, "verified")
        movie["duration"] = 120
        self.assertEqual(evaluate(movie, req)[0].eligibility, "excluded")

    def test_conflict_counterfactual_does_not_mutate_requirement(self):
        req = SearchRequest("watch", (), filters={"max_duration": 90})
        verified, unresolved, conflicts = match_records([self.movie()], req)
        self.assertFalse(verified)
        self.assertTrue(any("unlocks 1" in s for s in conflicts))
        self.assertEqual(req.filters["max_duration"], 90)

    def test_suggestion_is_scoped_and_ranked(self):
        services = AppServices(Settings(), "sample")
        req = SearchRequest("watch", (), suggestions=({**self.movie(), "source": "Participant-provided", "confirmed_details": True},))
        result = watch.search(req, services)
        self.assertLessEqual(len(result.candidates), 5)
        self.assertNotIn("movie", [c.id for c in watch.search(replace(req, suggestions=()), services).candidates])


class StorageTests(unittest.TestCase):
    def test_catalog_upserts_without_duplicate_records(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(url="", path=Path(directory) / "store.db")
            store.upsert_catalog("watch", [{"id": "a", "title": "A"}])
            store.upsert_catalog("watch", [{"id": "a", "title": "Updated"}])
            self.assertEqual(store.catalog("watch"), [{"id": "a", "title": "Updated"}])


class ImportTests(unittest.TestCase):
    def test_movie_unknowns_not_zero(self):
        movie = normalize_movie({"Title": "Test", "imdbID": "tt1", "Runtime": "N/A", "Genre": "N/A"})
        self.assertNotIn("duration", movie)
        self.assertFalse(movie["genres_known"])

    def test_game_keeps_platform_capacity_and_omits_completion_time(self):
        game = normalize_game({"id": 1, "name": "Test", "time_to_beat": 999,
                               "multiplayer_modes": [{"platform": {"name": "PC"}, "offlinemax": 4},
                                                     {"platform": {"name": "Console"}, "onlinemax": 8}]})
        self.assertNotIn("duration", game)
        self.assertEqual([(r["platform"], r["mode"], r["max_players"]) for r in game["multiplayer"]],
                         [("PC", "Local", 4), ("Console", "Online", 8)])

    @patch("core.media_apis.time.sleep")
    @patch("core.media_apis.requests.request")
    def test_rate_limit_retry(self, request, sleep):
        limited = Mock(status_code=429, headers={"Retry-After": "0"})
        ok = Mock(status_code=200); ok.json.return_value = {"ok": True}
        request.side_effect = [limited, ok]
        self.assertEqual(request_json("GET", "https://example.com"), {"ok": True})
        self.assertEqual(request.call_count, 2)


class RetrievalTests(unittest.TestCase):
    def test_typed_query_does_not_expand_to_every_catalog_title(self):
        documents = Mock()
        documents.search.return_value = {'found': 0, 'hits': []}
        watch.search(SearchRequest('watch', (Person('p', 'Pat', likes=('Comedy',)),), query='Toy Stroy'), self.services(documents))
        queries = [call.args[0]['q'] for call in documents.search.call_args_list]
        self.assertEqual(queries, ['Toy Stroy'])

    def services(self, documents):
        client = Mock()
        client.collections = Mock()
        client.collections.__getitem__ = Mock(return_value=Mock(documents=documents))
        return AppServices(Settings(api_key="test"), _client=client)

    def test_typesense_projection_checked_and_per_person_queries(self):
        documents = Mock()
        rows = [{"id": "a", "title": "A", "tags": ["Comedy"], "duration": 90, "source": "OMDb"},
                {"id": "b", "title": "B", "tags": ["Drama"], "source": "OMDb"},
                {"id": "c", "title": "C", "tags": ["Comedy"], "duration": 130, "source": "OMDb"}]
        documents.search.return_value = {"found": 3, "hits": [{"document": {"payload": json.dumps(r)}} for r in rows]}
        services = self.services(documents)
        req = SearchRequest("watch", (Person("p", "Pat", likes=("Comedy",)),), filters={"max_duration": 100})
        result = watch.search(req, services)
        self.assertEqual([c.id for c in result.candidates], ["a"])
        self.assertEqual([c.id for c in result.unresolved], ["b"])
        calls = [call.args[0] for call in documents.search.call_args_list]
        self.assertIn("Comedy", [c["q"] for c in calls])
        self.assertTrue(any(c["filter_by"] == "duration:<=100" for c in calls))

    def test_search_error_does_not_use_sample_fallback(self):
        documents = Mock()
        documents.search.side_effect = RuntimeError("upstream unavailable")
        with self.assertRaises(CategorySearchError):
            watch.search(SearchRequest("watch", ()), self.services(documents))

    @patch.dict("os.environ", {"TYPESENSE_HYBRID": "true"})
    def test_hybrid_uses_embedding_and_distinct_index(self):
        documents = Mock()
        documents.search.return_value = {"found": 0, "hits": []}
        services = self.services(documents)
        watch.search(SearchRequest("watch", (), query="thoughtful"), services)
        self.assertIn("embedding", documents.search.call_args_list[0].args[0]["query_by"])
        self.assertTrue(all(call.args[0].endswith("_media_hybrid") for call in services.client.collections.__getitem__.call_args_list))

    @patch.dict("os.environ", {"IGDB_CLIENT_ID": "test", "IGDB_CLIENT_SECRET": "secret"})
    @patch("core.media_apis.request_json")
    def test_token_cached_and_renewed(self, request):
        request.return_value = {"access_token": "test", "expires_in": 3600}
        client = IGDB(); client.authenticate(); client.authenticate()
        self.assertEqual(request.call_count, 1)
        client.expires = 0; client.authenticate()
        self.assertEqual(request.call_count, 2)


if __name__ == "__main__":
    unittest.main()
