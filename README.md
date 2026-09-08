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
- Real Typesense typo-tolerant searches and structured filters over the four starter catalogs.
- One common group-ranking rule: protect the lowest preference match, then improve the average.
- Up to three shortlisted choices; Love / Okay / Pass ballots; explicit confirmation after everyone has voted and nobody passes on that choice.
- Custom options reuse the same voting workflow without needing catalog search.
- Category state stays separate; preference and group changes clear stale results and votes.
- Explicit seeding, service health check, missing-category handling, and actionable search errors.

**The starter catalogs are fictional.** They exercise the real search infrastructure; they are not real restaurant, activity, movie, or game recommendations. Category owners replace them with sourced data. Geographic routing, semantic embeddings, automatic source scraping, saved accounts, and realtime multiplayer are not implemented.

Inputs persist across normal Streamlit reruns/category switches. Browser refresh or a new session may clear the group; durable session history is not part of this local v1.

## Work split

| Owner | Files |
|---|---|
| Person 1 | `main.py`, `core/`, `ui/`, setup/launch scripts, shared configuration and dependencies |
| Person 2 | `categories/eat.py`, `data/eat.json` |
| Person 3 | `categories/do.py`, `data/do.json` |
| Person 4 | `categories/watch.py`, `categories/play.py`, `categories/anything.py`, matching data files |

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

With the app running and the original starter catalogs seeded, run these additional checks against the real search server:

```sh
python -m scripts.verify_live
```

This checks seven typo, exclusion, budget, duration, dietary-option, and player-count searches. Update the expected fixture IDs when you replace the starter catalogs.

## GitHub workflow

Person 1 commits this baseline to your existing repository. Everyone pulls it and works on a small category branch. Open a PR after one functioning change; Person 1 checks the shared contract, merges, seeds that category, and exercises the UI. Keep shared dependency and contract edits with Person 1. This folder was not connected or pushed to GitHub because the repository URL was not supplied.

## Demo

1. Pick Eat and add two or more names.
2. Give one person Mexican likes and another Italian likes; save each.
3. Search with a $25 budget. Market Hall can match both within the fictional starter catalog.
4. Add an exclusion and rerun to demonstrate a real hard filter.
5. Shortlist two choices, switch to Shortlist, save every person's ballot, then confirm a consensus option.
6. Switch to Anything, type two original choices, and repeat the voting flow.

## Troubleshooting

- **No catalog:** run the explicit seed command while Typesense is running.
- **No search connection:** check `.env`, Developer settings, and `.runtime/typesense.log`.
- **Port 8501 occupied:** use the running app or stop its terminal before starting another instance.
- **Category not integrated:** verify its `get_spec`, `search`, and `seed` functions and inspect the terminal error.
- **Saved preferences missing after refresh:** start a new local decision; only in-session state is preserved.

Server downloads: https://typesense.org/docs/guide/install-typesense.html

Streamlit: https://docs.streamlit.io/get-started/installation
