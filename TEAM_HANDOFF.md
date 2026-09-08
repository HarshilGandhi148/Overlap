# Category handoff contract

Person 1 owns the app, group state, forms, ranking, cards, shortlist, and voting. Your category owns data, filters, and retrieval. Keep your work inside your assigned `categories/<name>.py` and `data/<name>.json` until a shared change is agreed.

## Your three functions

```python
from core.contracts import CategorySpec, SearchRequest, SearchResponse, SeedReport
from core.services import AppServices

def get_spec() -> CategorySpec:
    ...

def search(request: SearchRequest, services: AppServices) -> SearchResponse:
    ...

def seed(services: AppServices) -> SeedReport:
    ...
```

The shipped category starters already implement these functions through `CatalogProvider`. You can replace the implementation while preserving the inputs and outputs.

## get_spec

Return your stable category ID, label, title, description, filter fields, like options, and exclusion options. Shared field types are text, number, select, multiselect, and checkbox. All filter fields are group-wide hard constraints; each person's likes and avoids are separate. `main.py` generates the controls from your spec.

When you replace fictional catalog data with real sourced data, set `is_sample=False`. Do not remove the sample label while still using any fictional listings.

## search

`request` contains:

- `category_id`, `query`, `filters`, `limit` (30).
- `people`: each has a stable `id`, `name`, `likes`, and `avoids`.
- `custom_options`: used only by Anything.

Use `services.client` for the shared Typesense client. Use `services.collection_name(request.category_id)` for your collection. Never hardcode a teammate's collection name or API key.

Return `SearchResponse(candidates=(...), total_found=..., engine="Typesense")`. Each `Candidate` contains:

```python
Candidate(
    category_id="eat",
    id="stable-source-id",
    title="Listing title",
    description="Short useful description",
    facts={"Cost": "$20 / person", "Cuisine": "Italian"},
    tags=("Italian",),
    matched_likes={person.id: tuple(x for x in person.likes if x == "Italian")
                   for person in request.people},
    reasons=("Fits the selected group budget.",),
    source_url="https://example.com/the-actual-listing",
)
```

Replace the illustrative source URL with a real source or leave it `None`. The UI renders source links only for http/https URLs.

Important rules:

1. Return only candidates meeting every shared hard filter and every person's exclusions. Missing required data is not a match. Never relax constraints silently.
2. Empty query must support browsing by filters. Typo search should use Typesense's actual search behavior.
3. `matched_likes` contains only selected preference IDs the record supports. Person 1 handles fair group ranking; do not return fabricated satisfaction percentages.
4. Keep provider relevance order. Group ranking uses it to break ties.
5. IDs must be stable and unique within your category.
6. Raise `CategorySearchError` with a safe actionable message for operational failures. Zero matches is a valid empty SearchResponse, not a server error.
7. No Streamlit imports, cross-category imports, filesystem writes, data downloads, or indexing at import/search time.
8. Preserve explicit sample mode for local UI work if you use the shared provider. Never silently fall back from failed Typesense search to local filtering.

The initial shared provider supports cost, duration, city, indoor/outdoor setting, required dietary options, player-count range, and tag exclusions. For additional fields, coordinate a small change to the shared provider or implement category-specific search behind the same contract.

## seed

Keep a primary source copy outside Typesense. Define your collection and import records explicitly with stable IDs. Return counts and errors in `SeedReport`. Upserts are repeatable but do not remove stale records. Do not delete or rebuild another category's collection.

Run `python -m scripts.seed <category>` after catalog changes. Keep the real server running while seeding. Importing the module or pressing a UI button must not trigger seeding.

## Integration checklist

- Pull Person 1's baseline and branch for your category.
- Confirm the spec renders without editing `main.py`.
- Add source/license notes for real data to `data/README.md`.
- Verify one filter-first search, one typo query, one exclusion, and one zero-result case.
- Verify required-but-unknown attributes cannot slip through the hard filters.
- Run `python -m unittest discover -s tests -v` and a live search.
- Open a small PR. Person 1 merges, seeds, and verifies the shared screen immediately.

Person 4 should integrate Watch first, then the small Anything workflow, then Play. Stubs keep those tabs available in the meantime.
