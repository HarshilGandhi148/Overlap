# Overlap

Find your group's common ground. A Python + Streamlit app that runs on one laptop, with a local Typesense search server. No accounts or phone joining.

## Start on this Mac

Double-click **Start Overlap.command**, then open http://localhost:8501.

Or, from the project folder:

```sh
.venv/bin/python run.py
```

Keep that terminal running. Ctrl+C stops the app and any search server started by this launcher. It does not stop an unrelated existing search server.

The installed local setup stores its private key in `.env`, its search binary in `.tools/`, and its search data/logs in `.runtime/`. All are ignored by Git.

## Fresh clone / teammate setup

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m scripts.setup_local --download
python run.py --seed
```

Tested on macOS arm64 with Python 3.14.7, Streamlit 1.63.0, Typesense Python 2.0.0, and Typesense Server 30.2. The server download helper supports Intel and Apple Silicon Macs running macOS 13 or newer. On other platforms, use the included Docker Compose file or point `.env` to an existing Typesense server. Never commit your `.env`.

For Docker, create `.env`, install Docker separately, then run `docker compose up -d` and `python run.py --seed`. Do not start Docker and the native search server on the same port simultaneously.

For UI work without a server, run `python -m streamlit run main.py` and explicitly choose **Sample preview (offline)** in Developer settings. This mode is labeled and never silently substitutes for a failed Typesense search.

## What works

- Add, rename, and remove people on one shared screen.
- Eat, Do, Watch, Play, and Anything category navigation.
- Shared constraints and individually saved likes/exclusions.
- Real Typesense searches and structured filters over integrated restaurant, activity, movie and game catalogs.
- One common group-ranking rule: protect the lowest preference match, then improve the average.
- Up to three shortlisted choices; Love / Okay / Pass ballots; explicit confirmation after everyone has voted and nobody passes on that choice.
- Custom options reuse the same voting workflow without needing catalog search.
- Category state stays separate; preference and group changes clear stale results and votes.
- Explicit seeding, service health check, missing-category handling, and actionable search errors.

**Eat uses 50 real NYC restaurant records**, with optional estimated-cost, dietary and distance filters. See `docs/eat-integration.md` for importing its ignored local dataset. Watch and Play use imported OMDb/IGDB records in Typesense mode and separately labeled fictional fixtures in offline sample mode. Do uses real OpenStreetMap places plus contributor-supplied cost/duration metadata. Do supports semantic matching and geographic radius filters. Routing, opening-hours validation, saved accounts, and realtime multiplayer are not implemented.

## Person 4 / Watch, Play, Anything integration

The integrated local catalog contains 20 OMDb movies and 110 IGDB game records from Person 4's supplied SQLite database. Only catalog rows were imported; saved decisions were not copied. Provider records, credentials, and SQLite files remain in ignored local storage. Other teammates need their own authorized imports after cloning; those records are not bundled into Git.

Watch adds personal runtime limits and already-watched title/IMDb exclusions. Play adds local/online mode, platform/format, capacity, personal time, and optional ownership/equipment checks. Play time includes setup and teaching. Imported IGDB records lack reviewed session estimates, so the default is explicitly **0 = no time limit**; selecting a time limit moves unknown-duration games into **Needs confirmation**, never silently treats them as short games. Custom participant-confirmed suggestions can supply estimates for a specific decision.

Both categories support catalog-title lookup, custom suggestions, and explanations for excluded or unresolved options. Unresolved options cannot enter the shared vote. Our existing three-option voting flow, names page, and Do integration remain in place. Anything's supplied implementation was unchanged and continues to handle custom choices without Typesense.

Configure the provider keys shown in `.env.example`, then import and index explicitly:

```sh
python -m scripts.import_catalog watch
python -m scripts.import_catalog play --count 100
python -m scripts.seed watch
python -m scripts.seed play
python -m scripts.verify_media_live
```

Ordinary search uses the indexed catalog, with no OMDb/IGDB calls. Primary catalog storage is SQLite (`.runtime/overlap.sqlite3`); PostgreSQL is optional through `DATABASE_URL` and was not tested in this integration. Collections use `<prefix>_watch_media` and `<prefix>_play_media`; they do not replace Do or Eat indexes. `TYPESENSE_HYBRID=true` opts into separate `_media_hybrid` collections and requires reseeding. Default keyword/typo search is the verified mode. See `docs/watch-play-integration.md` for sources and assessments.

## Person 3 / Do integration

Do stays inside the shared Discover → Vote flow and uses the names added on the group page. Save a written preference, maximum time, and budget for each person. Everyone's limits are mandatory; the strictest time/budget wins. The nearby model supports the same 1–12 people as the shared app.

The default **Saved NYC demo** contains 50 real OSM records captured 2026-09-08. It is explicitly labeled as a saved snapshot. **Load live places** supports manual coordinates or browser location; loading can take longer and cost/duration coverage outside the enriched NYC set is limited. Radius/preference changes reuse an area for 30 minutes. Expired live areas refresh on the next search; if refresh fails, an existing same-location batch is labeled stale. Sources are in `data/README.md`.

Prepare the NYC collection using **Prepare / refresh NYC search** in Do, or run:

```sh
python -m scripts.seed do
python -m scripts.verify_do
```

The first seed downloads Typesense's `ts/all-MiniLM-L12-v2` embedding model on the search server and needs internet access. Do requires the real Typesense engine; offline sample preview deliberately does not imitate semantic search. It uses `<prefix>_do_nearby_v1`, separate from the other category collections. Search itself never imports data; only explicit preparation and the live-area loading step do.

Typesense performs geo, cost, duration, category-exclusion, and wheelchair filters and semantic search for each person's text. Python combines the scores with the submitted 70% opinion / 15% distance / 10% time / 5% cost formula. Shared voting and category interfaces remain unchanged. Results show up to 10 options and include source/estimate details under **Why this fits**.

Inputs persist across normal Streamlit reruns/category switches. Browser refresh or a new session may clear the group; durable session history is not part of this local v1.

## Work split

| Owner | Files |
|---|---|
| Person 1 | `main.py`, `core/`, `ui/`, setup/launch scripts, shared configuration and dependencies |
| Person 2 | `categories/eat.py`, `data/eat.json` |
| Person 3 | `categories/do.py`, `nearby/`, `data/nyc_places.json`, `data/nyc_enrichment.json` |
| Person 4 | Watch/Play/Anything category files, `core/media_*.py`, `core/storage.py`, `ui/media.py`, matching catalog/import files |

Read **TEAM_HANDOFF.md before changing category code**. Every category returns shared dataclasses; none of the category modules draws UI or imports main.py.

## Update a catalog

```sh
python -m scripts.seed eat
```

Or use `all`. Stable IDs are upserted, so rerunning an unchanged import does not duplicate records. Upsert does not delete records removed from your JSON; for a deliberately replaced catalog, use a new collection prefix and reseed. Original data remains in `data/`; Typesense holds the rebuildable search copy. There are no imports on UI reruns.

Each teammate should use their own local server. For a shared remote server, give each developer a distinct `TYPESENSE_COLLECTION_PREFIX`.

## Verify changes

```sh
python -m unittest discover -s tests -v
```

These checks cover hard filters, fair ranking, data contracts, state isolation, stale-decision invalidation, voting, and core Streamlit interaction. They use explicit sample mode so they do not depend on a running search server. Also seed and try a real Typesense search before merging a provider change.

With the real restaurant catalog imported and seeded, run these additional checks against the real search server:

```sh
python -m scripts.verify_live
```

This checks real Eat typo, distance, budget, dietary and exclusion searches. Run `python -m scripts.verify_do` for Do and `python -m scripts.verify_media_live` for Watch/Play.

## GitHub workflow

Person 1 commits this baseline to your existing repository. Everyone pulls it and works on a small category branch. Open a PR after one functioning change; Person 1 checks the shared contract, merges, seeds that category, and exercises the UI. Keep shared dependency and contract edits with Person 1. This folder was not connected or pushed to GitHub because the repository URL was not supplied.

## Demo

1. Pick Eat and add two or more names.
2. Save cuisine preferences for each person.
3. Search for `Litle Alley` to show typo tolerance; enter `40.75, -73.99` as the meeting point.
4. Add an exclusion and rerun to demonstrate a real hard filter.
5. Add choices to Vote, save every person's ballot, then confirm a consensus option.
6. Switch to Anything, type two original choices, and repeat the voting flow.

## Troubleshooting

- **No catalog:** run the explicit seed command while Typesense is running.
- **No search connection:** check `.env`, Developer settings, and `.runtime/typesense.log`.
- **Port 8501 occupied:** use the running app or stop its terminal before starting another instance.
- **Category not integrated:** verify its `get_spec`, `search`, and `seed` functions and inspect the terminal error.
- **Saved preferences missing after refresh:** start a new local decision; only in-session state is preserved.

Server downloads: https://typesense.org/docs/guide/install-typesense.html

Streamlit: https://docs.streamlit.io/get-started/installation

## Shared Google Places key

Eat and Do read `GOOGLE_MAPS_API_KEY` from ignored `.env`. Eat uses Places API (New) Text Search for meeting points and explicit restaurant enrichment; normal results remain Typesense searches over the imported catalog. Do live mode uses Nearby Search (New), one request for up to 20 activities, cached per loaded area for 30 minutes. Explicit refresh can make another request. The saved NYC demo remains OSM-based and does not spend API credit. Do ranks by group opinions (85%) and distance (15%), with radius and category exclusions. Cost, duration and wheelchair controls have been removed; legacy saved limits are ignored. No budget balance or automatic $5 spending cap is implemented.

After everyone has voted and the group confirms a consensus pick, a brief confetti animation plays once. Reduced-motion preferences suppress the animation.

Voting uses Love = 2, Okay = 1, Pass = 0. A Pass lowers the score without vetoing a choice. Results are ordered by total points; ties preserve shortlist order. All members must vote on all options before any final confirmation.

Project Members: Harshil Gandhi, Nathan Madzelan, Venkata Gummidi, Krish Pilaya
