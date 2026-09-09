"""Watch/Play retrieval behind the existing category contract."""
from dataclasses import replace
import json
import os
from core.catalog import CatalogProvider, quote
from core.contracts import CategorySearchError, SearchResponse, SeedReport
from core.media_matching import match_records
from core.ranking import rank_candidates
from core.storage import Store


class MediaCatalog(CatalogProvider):
    def lookup(self, query, services):
        if not query.strip():
            return []
        if services.mode == "sample":
            return [r for r in self.records() if query.casefold() in r["title"].casefold()][:10]
        try:
            result = services.client.collections[self.collection(services)].documents.search({
                "q": query.strip(), "query_by": "title", "prefix": True, "num_typos": 2,
                "per_page": 10, "exclude_fields": "embedding"})
            return [json.loads(h["document"]["payload"]) for h in result.get("hits", [])]
        except Exception:
            raise CategorySearchError("Title lookup failed. Check Typesense and index the imported catalog.") from None

    def collection(self, services):
        # A separate projection preserves the teammates' existing starter indexes.
        suffix = "media_hybrid" if os.getenv("TYPESENSE_HYBRID", "false").lower() == "true" else "media"
        return services.collection_name(self.spec.id) + "_" + suffix

    def projection(self, record):
        doc = {"id": str(record["id"]), "title": record["title"],
               "description": record.get("description", ""),
               "tags": list(dict.fromkeys(record.get("tags", []) + record.get("curated", {}).get("tags", []))),
               "payload": json.dumps(record)}
        if record.get("duration") is not None:
            doc["duration"] = record["duration"]
        return doc

    def seed(self, services):
        from typesense.exceptions import ObjectAlreadyExists
        records = Store().catalog(self.spec.id)
        if not records:
            raise CategorySearchError(f"Import the {self.spec.label} catalog first: python -m scripts.import_catalog {self.spec.id}. Offline samples remain available separately.")
        fields = [{"name": "title", "type": "string"}, {"name": "description", "type": "string"},
                  {"name": "tags", "type": "string[]", "facet": True},
                  {"name": "duration", "type": "int32", "optional": True},
                  {"name": "payload", "type": "string", "index": False}]
        if os.getenv("TYPESENSE_HYBRID", "false").lower() == "true":
            fields.append({"name": "embedding", "type": "float[]",
                           "embed": {"from": ["title", "description", "tags"],
                                     "model_config": {"model_name": "ts/all-MiniLM-L12-v2"}}})
        name = self.collection(services)
        try:
            services.client.collections.create({"name": name, "fields": fields})
        except ObjectAlreadyExists:
            pass
        report = services.client.collections[name].documents.import_([self.projection(r) for r in records], {"action": "upsert"})
        if isinstance(report, str):
            report = [json.loads(line) for line in report.splitlines() if line.strip()]
        errors = tuple("A catalog record could not be indexed; check its normalized fields." for r in report if not r.get("success"))
        return SeedReport(self.spec.id, len(report) - len(errors), len(errors), errors)

    def search(self, request, services):
        warnings, time_ms = [], None
        if services.mode == "sample":
            records = self.records()
            if request.query.strip():
                # Reuse the original preview's typo matching without its eligibility filters.
                preview = super().search(replace(request, filters={}, people=()), services)
                ids = {c.id for c in preview.candidates}
                records = [r for r in records if r["id"] in ids]
            engine = "Sample preview"
            warnings.append("Fictional sample preview; these results do not use Typesense or provider data.")
        else:
            engine = "Typesense"
            try:
                records_by_id = {}
                query_fields = "title,description,tags"
                if os.getenv("TYPESENSE_HYBRID", "false").lower() == "true":
                    query_fields += ",embedding"
                explicit_query = request.query.strip()
                queries = [explicit_query] if explicit_query else list(dict.fromkeys(
                    [" ".join(p.likes) for p in request.people if p.likes] + ['*']))
                # Pull the complete small imported catalog for diagnostics and Python rechecks.
                # Individual, fact-filtered queries provide relevance before the browse union.
                limits = [p.requirements.get("max_duration", 0) for p in request.people]
                limits += [request.filters.get("max_duration", 0)]
                filters = []
                if request.category_id == "watch" and any(limits):
                    filters.append(f"duration:<={min(v for v in limits if v)}")
                avoids = sorted({v for p in request.people for v in p.avoids})
                if avoids:
                    filters.append("tags:!=[" + ",".join(quote(v) for v in avoids) + "]")
                for query in queries:
                    page = 1
                    while True:
                        result = services.client.collections[self.collection(services)].documents.search({
                            "q": query, "query_by": query_fields, "per_page": 250, "page": page,
                            # An explicit query keeps its own complete result set for diagnostics.
                            # Browsing can merge preference searches; typed text must never expand to all titles.
                            "filter_by": " && ".join(filters) if query != "*" and not explicit_query else "", "prefix": True,
                            "num_typos": 2, "drop_tokens_threshold": 0,
                            "exclude_fields": "embedding"})
                        time_ms = (time_ms or 0) + result.get("search_time_ms", 0)
                        for hit in result.get("hits", []):
                            record = json.loads(hit["document"]["payload"])
                            records_by_id.setdefault(record["id"], record)
                        if page * 250 >= result.get("found", 0):
                            break
                        page += 1
                        if page > 20:
                            warnings.append("Search evaluated the first 5,000 hits per query; conflict counts describe that subset.")
                            break
                records = list(records_by_id.values())
            except CategorySearchError:
                raise
            except Exception as exc:
                raise CategorySearchError(f"{self.spec.label} search failed. Check Typesense and run python -m scripts.seed {self.spec.id} after importing. Existing catalog data has been retained.") from exc
        # Suggestions are decision scoped and never written to the shared search index.
        merged = {str(r["id"]): r for r in records}
        for record in request.suggestions:
            merged.setdefault(str(record["id"]), record)
        verified, unresolved, conflicts = match_records(list(merged.values()), request)
        ranked = rank_candidates(tuple(verified), request.people)[:min(request.limit, 5)]
        return SearchResponse(tuple(ranked), len(verified), tuple(warnings), engine, time_ms,
                              tuple(unresolved), tuple(conflicts))
