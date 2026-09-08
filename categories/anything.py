"""PERSON 4: custom choices reuse Person 1's shortlist and voting UI."""
from hashlib import sha256
from core.contracts import Candidate, CategorySpec, SearchResponse, SeedReport

SPEC = CategorySpec("anything", "Anything", "What are we deciding?",
                    "Bring your own options. Find agreement together.", is_sample=False, custom=True)


def get_spec():
    return SPEC


def search(request, services):
    seen, candidates = set(), []
    for text in request.custom_options:
        title = text.strip()
        if not title or title.casefold() in seen:
            continue
        seen.add(title.casefold())
        candidates.append(Candidate("anything", sha256(title.casefold().encode()).hexdigest()[:20],
                                    title, "Suggested by your group.", {"Type": "Custom choice"}))
    return SearchResponse(tuple(candidates[:request.limit]), len(candidates), engine="Your choices")


def seed(services):
    return SeedReport("anything", 0)
