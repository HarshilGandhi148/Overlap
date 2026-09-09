# Eat integration

Eat uses the shared group preferences, restaurant search and three-option Vote flow. Personal cuisine exclusions are mandatory; likes use shared fair ranking. No phone joining or alternate decision system was imported.

The local catalog has 50 real OpenStreetMap restaurants captured on 2026-09-08 from a Manhattan bounding box (40.73,-74.01,40.77,-73.97). A bounded Google Places test enriched the first ten records where names and locations matched; five acquired estimated costs. This is a snapshot, not a complete or live NYC directory. Source links and provenance are retained.

`data/eat_real.json` is the primary local source and is ignored by Git because it includes provider-enriched metadata. Typesense's `overlap_local_eat_restaurants` collection is its secondary search index. The six fictional restaurants in `eat.json` are used only in explicitly labeled Sample preview. Missing real data never silently switches to fictional listings.

For another laptop:

```sh
python3 -m pip install -r requirements.txt
# Configure local Typesense in .env; optional GOOGLE_MAPS_API_KEY enables enrichment/address lookup.
python3 -m scripts.import_eat --limit 50
python3 -m scripts.seed eat
python3 -m scripts.verify_live
python3 -m streamlit run main.py
```

The importer loads `.env`. With a configured Google key, importing explicitly makes up to one Google Text Search request per restaurant (subject to provider billing). Without a key it imports OSM only. Ordinary restaurant searches call Typesense, not Places. Address lookup uses Places API (New) Text Search and is cached; coordinates work without Google. Blank meeting point searches the snapshot; a supplied address that fails cannot silently disable distance filtering.

Cost filtering is off by default because many records have no price metadata. Enabling it excludes unknown prices. Dollar estimates are app-defined approximations from Google's categorical price tiers, not menu quotes or guaranteed spending limits. Dietary tags indicate listed options, not allergen safety. Opening hours are not used to claim a venue is open.

Attribution: © OpenStreetMap contributors, ODbL: https://www.openstreetmap.org/copyright. Enriched fields: Google Maps. Check provider terms before redistributing enriched data. API keys and imported provider data remain ignored.

References used to repair the importer: https://wiki.openstreetmap.org/wiki/Key:diet and https://developers.google.com/maps/documentation/places/web-service/reference/rest/v1/places#PriceLevel.

Run `python3 -m unittest discover -s tests -v` for shared and Eat regressions; `python3 -m scripts.verify_live` checks real Typesense typo, geo, dietary, budget and exclusion searches. Existing Do and media live verifiers remain separate.
