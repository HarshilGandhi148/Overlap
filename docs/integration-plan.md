# Overlap — Person 1 implementation and integration plan

## Decisions and boundaries

- Working name: Overlap. Desktop browser app running on one laptop at localhost.
- Python 3 with Streamlit as the recommended framework default. The user confirmed localhost rather than selecting a framework. One shared screen; people enter preferences in turn. No accounts, room links, phone joining, or remote hosting.
- Person 1 owns main.py, infrastructure, shared UI, group state, ranking, and final-choice workflow.
- Person 2 owns Eat. Person 3 owns Do. Person 4 owns Watch, Play, and Anything. “Water” was confirmed to mean Watch.
- The inspected Desktop/Typesense directory is empty. The GitHub repository URL and its contents have not been provided, so proposed paths are a contract to agree with the team, not an inventory of existing code.
- This document and the accompanying visual are planning artifacts. They do not implement the app or modify the Desktop folder.

## What the app does

Use a persistent sidebar for the group: add/remove names, choose whose preferences to edit, and reset the decision. Across the main panel, show Eat, Do, Watch, Play, Anything. Only the selected category executes.

Each category has the same workflow:

1. Set shared must-haves once: category-specific budget, time, location, or requirements. These apply to everyone. The group chooses the strictest agreed limits; the app does not infer them from free text.
2. Each person selects things they like and things to exclude. An explicit “No preference” choice leaves their likes empty. Everyone enters on the same screen; preferences are not private.
3. Search descriptions using the common search box and press Find our overlap. The shared search text describes what the group wants, while explicit controls carry hard requirements.
4. Show ranked options with factual metadata, each person's preference matches, and source links. Use plain reasons, not an invented percentage probability of satisfaction.
5. Add up to three options to a shortlist. In shortlist view, choose a person and mark each option Love / Okay / Pass, then save their ballot. Show missing ballots.
6. Highlight options with no Pass votes only once everyone has voted. The group explicitly confirms a final choice. A tie stays a tie until the group chooses. If every option has a Pass, offer returning to preferences.

A member's saved category preferences and the current shortlist survive Streamlit reruns and category switches. A new browser session or hard refresh may reset the session; this is an explicit v1 limitation. Refresh persistence and saved groups are deferred.

## UI design

- Wide desktop layout, a restrained neutral surface, violet accent, clear type, and generous spacing. Use Streamlit native controls with theme configuration; avoid brittle CSS selectors into Streamlit's internal markup.
- Left sidebar: Overlap, group members, Add person, active person, and Start over. Do not expose Typesense collections or keys in normal app flows.
- Main header: category navigation and a small Preferences / Shortlist view switch.
- Main body: category title, shared search input, compact must-have controls, current person's Like / Exclude controls, Save preferences, and Find our overlap.
- Results: two columns when space permits; title, short description, 2–4 category-relevant facts, source link, preference-match explanations, and shortlist control. Missing images use a plain category fallback, not a broken image.
- Shortlist: at most three choices; common vote controls for the active person; final selection card.
- Anything replaces catalog filters with a multiline custom-options field. User options enter the same shortlist/voting workflow. This mode does not pretend to have catalog-derived metadata or personalized search scores.
- Loading, not-yet-integrated, empty-result, and search-unavailable states must be designed before visual polish. No automatic replacement of a failed real search with sample results.
- The visual sketch uses explicitly labeled sample options. Its custom styling is a visual direction, not a promise of pixel-identical Streamlit rendering.

## Ownership and proposed layout

```text
Typesense/
  main.py                  Person 1: entrypoint, page orchestration
  core/
    contracts.py           Person 1: shared data contracts
    registry.py            Person 1: category registration
    services.py            Person 1: configured Typesense client
    state.py               Person 1: session initialization and invalidation
    ranking.py             Person 1: one group-ranking policy
  ui/
    shell.py               Person 1: layout, navigation, group controls
    forms.py               Person 1: shared filter/preference renderer
    results.py             Person 1: cards, shortlist, votes, final choice
  categories/
    eat.py                 Person 2
    do.py                  Person 3
    watch.py               Person 4
    play.py                Person 4
    anything.py            Person 4
  data/
    eat.json               Person 2: original catalog and provenance
    do.json                Person 3
    watch.json             Person 4
    play.json              Person 4
  scripts/
    seed.py                Person 1: runs each category's explicit seed function
  .env.example             Person 1: configuration names, no secrets
  .gitignore               Person 1
  requirements.txt         Person 1: one verified pinned dependency set
  compose.yaml             Person 1: optional local Typesense server
  README.md                Person 1: exact shared startup sequence
```

Teammates own their category modules and data. Person 1 owns shared files and dependencies. Category modules do not import main.py or another category, call Streamlit, modify session state, initialize independent clients, or download/reindex data during import/search.

## Shared module contract — agree before branching

Each category exposes these three entrypoints:

```python
def get_spec() -> CategorySpec: ...

def search(request: SearchRequest, services: AppServices) -> SearchResponse: ...

def seed(services: AppServices) -> SeedReport: ...
```

Use standard Python dataclasses in core/contracts.py. Native Python calls are sufficient; there is no separate HTTP API between categories and main.py.

| Contract | Required contents and behavior |
|---|---|
| CategorySpec | id, label, description, filter_fields, like_options, avoid_options. IDs: eat, do, watch, play, anything. |
| FilterField | key, label, kind, default; kind is text, number, select, multiselect, or checkbox. Choices for selection fields; minimum/maximum/step for number fields. These are shared group constraints. |
| Person | stable id, name, likes, avoids. Likes and avoids are category-specific canonical option IDs. Display labels come from CategorySpec. |
| SearchRequest | category_id, query, filters, people, limit (30 by default), custom_options (empty except Anything). |
| Candidate | category_id, stable id, title, description, facts (label/value strings), tags, source_url (optional), image_url (optional), matched_likes (person ID to selected like IDs), reasons (factual short strings). |
| SearchResponse | candidates, total_found (optional), warnings. candidates are already checked against every explicit hard constraint and exclusion. |
| AppServices | configured client and a category-to-collection-name function. The shared client is reused, not created per query. |
| SeedReport | category_id, imported count, failed count, error details. Imports are explicit and repeatable using stable IDs and upsert. |

All functions return plain data. Person 1 renders every screen, ranks candidates, stores shortlists, and records votes. Providers return candidates in search-relevance order; that order is the final ranking tiebreaker.

Provider responsibilities:

- Obtain and document their dataset and source/license information. Normalize records to a category collection and keep the original catalog as JSON.
- Define category-specific filter controls and canonical like/exclude options through get_spec(). Only advertise filters that their data can support.
- Translate group filters and all participants' exclusions into real filtering. Treat missing required attributes as unknown, not as a successful match. A restaurant menu label is not proof of allergen safety.
- Use Typesense for catalog search. Return correct records even when the free-text query is empty, permitting filter-first browsing.
- Populate matched_likes using only the selected preference IDs that the result actually matches. Do not put unsupported LLM guesses or raw relevance scores here.
- Return a clear warning for known data limitations; raise a shared CategorySearchError for operational failures so Person 1 can show a retry state.
- Supply 5 small sample records and one expected request/result pair early, then their real catalog and seed function. Mark sample data explicitly.
- Anything may return custom options directly and use an empty seed operation because original choices and voting are local session state. It does not need an artificial Typesense dependency.

First baseline filters: Eat—agreed budget per person, city/location, required dietary options only when supported; Do—budget, duration, indoor/outdoor; Watch—runtime and genres; Play—player count, duration, complexity; Anything—custom options. Category owners finalize exact choices against their data before handing over the spec.

## main.py orchestration and shared state

main.py stays small and delegates helpers:

```text
Configure page → initialize shared session state → load registered category
→ render group + category controls → save the active person's preferences
→ on Find: construct SearchRequest → category.search(request, services)
→ validate response → rank candidates → store results → render cards
→ update shortlist/votes → explicitly confirm a final choice
```

Store people globally; store filters, likes/exclusions, custom options, results, shortlist, votes, and confirmed choice under each category ID. Use widget keys that include category ID + person ID + field ID, not display names or list positions. The active person ID is global.

Use Streamlit forms for saving preferences and a Find button for searches. Search results are therefore not requested on every keystroke in the first version. Use session state for reruns and cache_resource only for the reusable Typesense client, never for mutable group preferences.

On a saved query/filter/preference/custom-option change, invalidate that category's old results, shortlist, votes, and final choice. Adding/removing a person invalidates these derived values across categories. Changing category alone preserves state. SearchUnavailable is distinct from zero matches. Missing optional category modules appear disabled with a brief status; unexpected failures are logged and surfaced rather than silently hidden.

## Shared ranking and voting

Apply hard constraints before ranking; the module is responsible for enforcing them and Person 1 tests this contract with fixtures.

For each person with at least one explicit like, compute score = number of matched selected likes / number of selected likes. Validate and deduplicate matched IDs against that person's actual selections. People with no likes are neutral and omitted from these scores. Rank the returned candidate pool by highest minimum person score, then highest average score, then the provider's original relevance order. If everybody is neutral, preserve provider relevance order. This ranking compares retrieved candidates; it does not claim a globally optimal choice across the entire catalog.

Explain that this is a simple preference-match rule. It is not a learned satisfaction score. Render concrete matched tags per person instead of a probability label. Hard exclusions are never relaxed by this ranking rule.

Votes are stored by category + candidate ID + person ID. Each person has one current ballot per option and may revise it. Changing the shortlist invalidates final confirmation and requires complete votes for its current options. Love = 2, Okay = 1, Pass = 0; once ballots are complete, only no-Pass options are consensus candidates, ordered by points. No automatic winner is declared on incomplete voting or a tie.

## Local infrastructure and Git integration

- Local UI launch: python3 -m streamlit run main.py. Streamlit serves the browser UI on localhost; no separate frontend build is needed.
- Initial runtime dependencies: streamlit, typesense, python-dotenv. Pin exact versions after installing and smoke-testing one shared environment. Use the same tested Python minor version across the team; Python 3.14.7 was observed locally, but package compatibility must be checked during setup.
- Use one local Typesense instance for the demo, ideally through Docker if installed. Bind it to loopback, mount a persistent local data directory, and require a nonempty API key. If the team already has a sponsor cluster, the same host/port/protocol/key settings can point to it; that configuration requires internet even though the UI remains local.
- Configuration keys: TYPESENSE_HOST, TYPESENSE_PORT, TYPESENSE_PROTOCOL, TYPESENSE_API_KEY, TYPESENSE_COLLECTION_PREFIX. Each developer/demo environment uses its own prefix; each category has its own collection.
- Originals remain in data/*.json. Typesense stores rebuildable search copies. Seed only via the explicit command; never rebuild during Streamlit reruns. Report failed imports before the demo.
- Keep .env, .venv, caches, local server data, and credentials out of Git. Commit .env.example and redistributable catalogs/fixtures with provenance.
- Person 1 merges a minimal shell, contracts, registry, and fixtures first. Everyone branches from that baseline.
- Teammates open small PRs that change their category/data files. Person 1 merges the category, registers it, seeds its collection, and runs the full workflow immediately.
- Shared contract changes go through Person 1 and get announced to all teammates before anyone adopts them. Dependencies are requested through Person 1 to prevent competing lock/pin changes.
- Person 4 starts with Watch and Anything, then adds Play. This order puts one substantial catalog and the small custom-choice workflow ahead of a third integration burden.

## Person 1 build order

1. Agree the contract and category names with all teammates. Confirm repository setup, tested Python version, Typesense access, and dependency pins.
2. Build the shell, member editor, category selector, shared forms, and state initialization using one explicitly labeled sample provider. Publish the baseline for everyone.
3. Finish result cards, preference explanations, shortlist, voting, and final confirmation using deterministic fixtures.
4. Add Typesense service initialization, health diagnostics, category registration, and explicit seeding. Keep diagnostics in a development panel rather than the customer flow.
5. Integrate the first working category and complete an end-to-end real search immediately. Repeat per category; do not defer all integration to the end.
6. Polish empty/error states and desktop layout. Prepare one deterministic local demonstration per integrated category and rehearse the transition between them.

The first useful milestone is: one category → two people → hard filters respected → real Typesense results → shortlist → complete voting → final choice.

## Acceptance checks

- A new teammate can follow README, configure the service, seed one catalog, and launch the app locally.
- All implemented category specs render through shared controls without category-owned Streamlit code.
- Switching categories preserves each category's inputs; votes and preferences never leak between categories.
- Duplicate display names are safe because stable IDs are used. Removing a person clears their derived contributions. At least one person is required to search; the UI starts with two editable names.
- Empty query/filter-first search, ordinary search, and a typo query return expected fixture records.
- Hard exclusions/budget limits never appear as relaxed results. A zero-result search offers editing constraints without changing them automatically.
- Ranking handles conflicting likes, no-preference members, ties, and unknown data consistently.
- Shortlist ballots are complete before consensus is shown; one Pass blocks consensus for that option. A new preference or group change clears stale decisions.
- Repeated reruns and repeated seed commands do not duplicate source records or unintentionally reindex data.
- Unavailable Typesense, an unseeded collection, a missing category, invalid data, and an empty catalog yield distinct understandable states; the rest of the app can still render.
- Anything works end to end without a catalog, and its results are clearly user-supplied.
- The demo uses the same main branch, data snapshot, and environment that passed these checks. No live source download is necessary during the presentation.

## Documentation used

- Streamlit local installation: https://docs.streamlit.io/get-started/installation
- Session state: https://docs.streamlit.io/develop/api-reference/caching-and-state/st.session_state
- Forms: https://docs.streamlit.io/develop/api-reference/execution-flow/st.form
- Resource caching: https://docs.streamlit.io/develop/api-reference/caching-and-state/st.cache_resource
- GitHub flow: https://docs.github.com/en/get-started/using-github/github-flow
