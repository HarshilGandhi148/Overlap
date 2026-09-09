"""Import provider facts to primary storage. Index separately with scripts.seed."""
import argparse
import json
from pathlib import Path
from core.contracts import CategorySearchError
from core.media_apis import OMDb, IGDB
from core.services import ROOT, Settings
from core.storage import Store


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["watch", "play"])
    parser.add_argument("--ids", help="Text file of curated IMDb IDs, one per line")
    parser.add_argument("--title", help="Look up and import a movie title or matching games")
    parser.add_argument("--count", type=int, default=100, help="Multiplayer IGDB import count, up to 500")
    parser.add_argument("--curation", help="JSON object keyed by provider ID, with source-attributed Play assessments")
    args = parser.parse_args()
    Settings.from_env()
    store = Store()
    curation = json.loads(Path(args.curation).read_text(encoding="utf-8")) if args.curation else {}
    imported, failed = 0, 0
    if args.mode == "watch":
        client = OMDb()
        path = Path(args.ids) if args.ids else ROOT / "data" / "movie_ids.txt"
        values = [args.title] if args.title else [s.strip() for s in path.read_text().splitlines() if s.strip() and not s.startswith("#")]
        for value in values:
            try:
                record = client.lookup(value)
                store.upsert_catalog("watch", [record])
                imported += 1
            except CategorySearchError as exc:
                failed += 1
                print(str(exc))
    else:
        client = IGDB()
        records = client.search(args.title) if args.title else client.import_multiplayer(args.count)
        existing = {r["id"]: r for r in store.catalog("play")}
        for record in records:
            assessment = curation.get(record["provider_id"], existing.get(record["id"], {}).get("curated"))
            if assessment:
                if not assessment.get("source"):
                    raise CategorySearchError("Every curated assessment needs a source.")
                for key in ("session_max", "setup_minutes", "teaching_minutes", "controllers_per_player"):
                    value = assessment.get(key)
                    if value is not None and (type(value) is not int or value < 0):
                        raise CategorySearchError(f"Curated {key} must be a nonnegative integer or null.")
                for key in ("mixed_experience", "replayable"):
                    if assessment.get(key) is not None and type(assessment[key]) is not bool:
                        raise CategorySearchError(f"Curated {key} must be true, false, or null.")
                record["curated"] = assessment
        store.upsert_catalog("play", records)
        imported = len(records)
    print(f"{imported} imported, {failed} failed into {store.label}. Existing records retained. Run python -m scripts.seed {args.mode} to update search.")
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    try:
        main()
    except CategorySearchError as exc:
        print(str(exc))
        raise SystemExit(1)
