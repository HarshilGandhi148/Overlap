# Starter catalogs

Records in `eat.json`, `watch.json`, `play.json`, and the unused legacy `do.json` are **fictional fixtures created for this app**. Titles, prices, durations, and menu options are illustrative and must not be presented as verified real-world listings.

The integrated Do category uses `nyc_places.json`: 50 real OpenStreetMap elements captured by Person 3 through Overpass on 2026-09-08, with source and retrieval metadata in the file. `nyc_enrichment.json` adds contributor-supplied descriptions, admission costs, estimated visit lengths, dates, and source links. These metadata values were carried over from the submission, not reverified during integration. All visit lengths and some costs are estimates; check current venue details.

Attribution: © OpenStreetMap contributors, ODbL — https://www.openstreetmap.org/copyright. Keep this attribution with redistributed OSM-derived data. The saved NYC demo is explicitly labeled as a snapshot. Live mode fetches Overpass independently and never silently falls back to the snapshot. Unknown cost or duration fails mandatory limits.

Category owners replace their matching file with sourced data and set `CategorySpec.is_sample=False` only when the data is real. Include provenance, license/attribution requirements, and last-checked dates here. Keep the original catalog in Git only when redistribution is permitted; otherwise commit a small permitted fixture and documented import instructions.

Typesense is a secondary search index. These files are the original source for the starter catalogs. Changing a source file requires an explicit seed operation; no data imports run during UI reruns.

## Watch / Play provider records

Person 4 supplied 20 OMDb movie records and 110 IGDB game records in their local SQLite database. The integration imports only those catalog rows into `.runtime/overlap.sqlite3`, which is ignored by Git. `watch.json` and `play.json` remain separate fictional offline fixtures; `movie_ids.txt` is a small IMDb ID list for explicit imports, not movie metadata. Ordinary searches do not call provider APIs.

Record source links, provider IDs, and import dates are retained. Provider metadata was not independently reverified during this code integration. Imported games have no curated session/setup/teaching estimates; missing facts remain unknown. See https://www.omdbapi.com/ and https://api-docs.igdb.com/ for provider attribution and usage terms before redistributing imports.

## Eat restaurant records

`eat_real.json` is an ignored local snapshot of 50 NYC OSM restaurants, with a small Google Places enrichment. Five records have rough app-defined price estimates from Google price tiers. Missing prices remain unknown and fail an enabled budget filter. Ordinary Eat searches use Typesense; the fictional `eat.json` is used only in explicit sample mode. See `docs/eat-integration.md` for provenance, attribution and rebuild instructions.
