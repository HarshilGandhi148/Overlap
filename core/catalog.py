"""Reusable starter provider. Teammates may replace it behind the same contract."""
import json
from difflib import SequenceMatcher
from pathlib import Path
import re
from core.contracts import Candidate, CategorySearchError, CategorySpec, SearchRequest, SearchResponse, SeedReport
from core.services import AppServices, ROOT


def quote(value: str) -> str:
    if any(c in value for c in ("`", "\n", "\r")):
        raise CategorySearchError("Filter values cannot contain backticks or newlines.")
    return f"`{value}`"


def filter_expression(request: SearchRequest) -> str:
    parts = []
    filters = request.filters
    if "budget" in filters:
        parts.append(f"cost:<={float(filters['budget'])}")
    if "max_duration" in filters:
        parts.append(f"duration:<={int(filters['max_duration'])}")
    if "players" in filters:
        players = int(filters["players"])
        parts.extend((f"players_min:<={players}", f"players_max:>={players}"))
    if filters.get("setting") not in (None, "Any"):
        parts.append(f"setting:={quote(filters['setting'])}")
    if filters.get("city", "").strip():
        parts.append(f"city:={quote(filters['city'].strip())}")
    for option in filters.get("dietary_options", []):
        parts.append(f"dietary_options:={quote(option)}")
    avoids = sorted({v for p in request.people for v in p.avoids})
    if avoids:
        parts.append("tags:!=[" + ",".join(quote(v) for v in avoids) + "]")
    return " && ".join(parts)


def eligible(record: dict, request: SearchRequest) -> bool:
    f = request.filters
    if "budget" in f and (record.get("cost") is None or record["cost"] > f["budget"]):
        return False
    if "max_duration" in f and (record.get("duration") is None or record["duration"] > f["max_duration"]):
        return False
    if "players" in f and not (record.get("players_min", 999) <= f["players"] <= record.get("players_max", -1)):
        return False
    if f.get("setting") not in (None, "Any") and record.get("setting") != f["setting"]:
        return False
    if f.get("city", "").strip() and record.get("city", "").casefold() != f["city"].strip().casefold():
        return False
    if not set(f.get("dietary_options", [])) <= set(record.get("dietary_options", [])):
        return False
    return not {v for p in request.people for v in p.avoids}.intersection(record.get("tags", []))


def to_candidate(record: dict, request: SearchRequest) -> Candidate:
    tags = tuple(record.get("tags", []))
    facts = {}
    if "cost" in record:
        facts["Cost"] = "Free" if record["cost"] == 0 else f"${record['cost']:g} / person"
    if "duration" in record:
        facts["Time"] = f"{record['duration']} min"
    if "city" in record:
        facts["Location"] = record["city"]
    if "setting" in record:
        facts["Setting"] = record["setting"]
    if "players_min" in record:
        facts["Players"] = f"{record['players_min']}–{record['players_max']}"
    return Candidate(request.category_id, str(record["id"]), record["title"],
                     record.get("description", ""), facts, tags,
                     {p.id: tuple(v for v in p.likes if v in tags) for p in request.people},
                     ("Fits the selected group constraints.",),
                     record.get("source_url"), record.get("image_url"))


class CatalogProvider:
    def __init__(self, spec: CategorySpec):
        self.spec = spec

    def records(self) -> list[dict]:
        path = ROOT / "data" / f"{self.spec.id}.json"
        try:
            records = json.loads(path.read_text())
            if not isinstance(records, list):
                raise ValueError("Expected a list")
            seen = set()
            for record in records:
                if not isinstance(record, dict) or not record.get("id") or not record.get("title"):
                    raise ValueError("Every record needs id and title")
                if record["id"] in seen:
                    raise ValueError("Duplicate record ID")
                seen.add(record["id"])
            return records
        except (OSError, ValueError, TypeError) as exc:
            raise CategorySearchError(f"Could not load data/{self.spec.id}.json. Check its JSON and record IDs.") from exc

    def search(self, request: SearchRequest, services: AppServices) -> SearchResponse:
        if services.mode == "sample":
            records = [r for r in self.records() if eligible(r, request)]
            if request.query.strip():
                tokens = re.findall(r"\w+", request.query.lower())
                def relevant(r):
                    words = re.findall(r"\w+", " ".join([r['title'], r.get('description', ''), *r.get('tags', [])]).lower())
                    return all(any(t in w or SequenceMatcher(None, t, w).ratio() >= .78 for w in words) for t in tokens)
                records = [r for r in records if relevant(r)]
            return SearchResponse(tuple(to_candidate(r, request) for r in records[:request.limit]),
                                  len(records), ("Explicit sample preview; these results do not use Typesense.",), "Sample preview")
        try:
            params = {"q": request.query.strip() or "*", "query_by": "title,description,tags",
                      "per_page": min(request.limit, 250), "num_typos": 2, "prefix": True,
                      "filter_by": filter_expression(request)}
            result = services.client.collections[services.collection_name(self.spec.id)].documents.search(params)
            records = [h["document"] for h in result.get("hits", [])]
            candidates = tuple(to_candidate(r, request) for r in records if eligible(r, request))
            return SearchResponse(candidates, result.get("found"), (), "Typesense", result.get("search_time_ms"))
        except CategorySearchError:
            raise
        except Exception as exc:
            from typesense.exceptions import ObjectNotFound, RequestUnauthorized
            if isinstance(exc, ObjectNotFound):
                message = f"The {self.spec.label} catalog has not been indexed. Run python -m scripts.seed {self.spec.id}."
            elif isinstance(exc, RequestUnauthorized):
                message = "Typesense rejected the API key. Check the server and .env configuration."
            else:
                message = "Typesense search is unavailable. Check the local server and Developer settings, then retry."
            raise CategorySearchError(message) from exc

    def seed(self, services: AppServices) -> SeedReport:
        from typesense.exceptions import ObjectAlreadyExists
        name = services.collection_name(self.spec.id)
        fields = [{"name": "title", "type": "string"}, {"name": "description", "type": "string"},
                  {"name": "tags", "type": "string[]", "facet": True}]
        for field_name, kind in [("cost", "float"), ("duration", "int32"), ("players_min", "int32"),
                                  ("players_max", "int32"), ("city", "string"), ("setting", "string"),
                                  ("dietary_options", "string[]")]:
            fields.append({"name": field_name, "type": kind, "optional": True, "facet": True})
        try:
            services.client.collections.create({"name": name, "fields": fields})
        except ObjectAlreadyExists:
            pass
        records = self.records()
        if not records:
            return SeedReport(self.spec.id, 0)
        report = services.client.collections[name].documents.import_(records, {"action": "upsert"})
        if isinstance(report, str):
            report = [json.loads(line) for line in report.splitlines() if line.strip()]
        errors = tuple(str(r.get("error", "Import failed")) for r in report if not r.get("success"))
        return SeedReport(self.spec.id, sum(bool(r.get("success")) for r in report), len(errors), errors)
