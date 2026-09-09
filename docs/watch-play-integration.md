# Watch / Play integration

Person 4's media retrieval and matching now run inside the shared Overlap app. The names page, Discover/Vote navigation, three-choice vote, and Do integration remain intact. Source-only data storage was integrated; the submission's alternative global voting phases and saved-decision UI were not substituted for the shared workflow.

## Data and setup

The supplied local catalog contains 20 OMDb movies and 110 IGDB game records. The GitHub working folder stores them in ignored `.runtime/overlap.sqlite3`. Keys live in ignored `.env`. Import commands are explicit; searches use Typesense, not live provider calls. A fresh clone needs its own provider keys and imports as described in README.md.

`python -m scripts.import_catalog watch` uses `data/movie_ids.txt`. Use `--ids path/to/ids.txt` for a larger selection or `--title "Movie title"` for one movie. `python -m scripts.import_catalog play --count 100` imports multiplayer records; `--title "Game title"` imports matching games. Upserts preserve existing records. Index with `python -m scripts.seed watch` and `python -m scripts.seed play`.

## Matching and unknowns

Typesense retrieves catalog records with title prefix/typo matching and preference queries. Typed queries stay scoped to those matches rather than silently broadening to the whole catalog. Python checks runtime, exclusions, platform-specific capacity, ownership, equipment, and supplied requirements. With no typed query, a catalog browse supports neutral members and conflict explanations.

IGDB provides platform/multiplayer information, not reliable session, setup, or teaching duration. The default Play time is explicitly zero (no limit); a selected time limit requires known total timing. Unknown requirements are displayed under Needs confirmation and cannot be voted on. Optional likes do not override hard requirements. Participant-supplied suggestions are labeled and must be explicitly confirmed.

Reviewed Play assessments can be supplied to `scripts.import_catalog play --curation path/to/assessments.json`, keyed by provider ID. Require a source and nonnegative integer fields `session_max`, `setup_minutes`, `teaching_minutes`; optional fields include `equipment`, `controllers_per_player`, `mixed_experience`, `replayable`, and `tags`. Unprovided facts remain unknown. No real-game timing assessments were invented in this merge.

## Verification

Run `python -m unittest discover -s tests -v` and, after imports/seeding, `python -m scripts.verify_media_live`. The live script checks both provider catalogs, real Typesense retrieval, typo lookup, typed-query isolation, runtime/exclusions, platform/player capacity, and unresolved game timing.

Anything is unchanged: it deduplicates participant choices and uses shared voting, without needing Typesense. PostgreSQL and optional hybrid embeddings are available configuration paths but are not part of the default tested media setup.

Sources: [OMDb](https://www.omdbapi.com/), [IGDB](https://api-docs.igdb.com/). Review provider terms before redistributing imported records.
