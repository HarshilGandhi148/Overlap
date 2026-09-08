# Starter catalogs

All records in these four JSON files are **fictional fixtures created for this app**. Titles, prices, durations, and menu options are illustrative and must not be presented as verified real-world listings. They can be indexed into a real Typesense instance to exercise the complete integration.

Category owners replace their matching file with sourced data and set `CategorySpec.is_sample=False` only when the data is real. Include provenance, license/attribution requirements, and last-checked dates here. Keep the original catalog in Git only when redistribution is permitted; otherwise commit a small permitted fixture and documented import instructions.

Typesense is a secondary search index. These files are the original source for the starter catalogs. Changing a source file requires an explicit seed operation; no data imports run during UI reruns.
