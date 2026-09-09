"""Watch/Play requirements are checked in Python, including unresolved facts."""
from dataclasses import replace
from core.catalog import to_candidate
from core.contracts import SearchRequest


def evaluate(record: dict, request: SearchRequest):
    blocked, unknown, reasons = [], [], []
    tags = set(record.get("tags", []))
    manual = record.get("source") == "Participant-provided"

    def maximum(value, limit, label):
        if not limit:
            return
        if value is None:
            unknown.append(f"{label} is unknown")
        elif value > limit:
            blocked.append(f"{label} exceeds {limit} min")
        else:
            reasons.append(f"{label} fits the {limit}-minute limit.")

    for person in request.people:
        if person.avoids:
            if not record.get("genres_known", bool(tags)):
                unknown.append(f"{person.name}: excluded genres cannot be checked")
            elif tags.intersection(person.avoids):
                blocked.append(f"{person.name}: excluded {', '.join(sorted(tags.intersection(person.avoids)))}")
        watched = {str(v).strip().casefold() for v in person.requirements.get("watched", [])}
        if str(record["id"]).casefold() in watched or record["title"].casefold() in watched:
            blocked.append(f"{person.name}: already watched")

    if request.category_id == "watch":
        maximum(record.get("duration"), request.filters.get("max_duration"), "Runtime")
        for person in request.people:
            maximum(record.get("duration"), person.requirements.get("max_duration"), f"{person.name}'s runtime")
    else:
        f = request.filters
        fmt = record.get("format", "Video")
        if f.get("format", "Any") != "Any" and fmt != f["format"]:
            blocked.append("Different game format")
        curated = record.get("curated", {})
        times = [curated.get(k) for k in ("session_max", "setup_minutes", "teaching_minutes")]
        total = sum(times) if all(v is not None for v in times) else None
        maximum(total, f.get("max_duration"), "Play, setup and teaching time")
        for person in request.people:
            maximum(total, person.requirements.get("max_duration"), f"{person.name}'s total time")
        players, mode, platform = int(f.get("players", 2)), f.get("play_mode", "Local"), f.get("platform", "Any")
        configs = [c for c in record.get("multiplayer", [])
                   if c.get("mode") == mode and (platform == "Any" or c.get("platform") == platform)]
        suitable = [c for c in configs if c.get("max_players") is not None and c["max_players"] >= players
                    and c.get("min_players", 1) <= players]
        if not suitable:
            if configs and all(c.get("max_players") is not None for c in configs):
                blocked.append(f"Does not support {players} {mode.lower()} players on {platform}")
            else:
                unknown.append(f"Capacity for {players} {mode.lower()} players on {platform} is unverified")
        else:
            reasons.append(f"Supports {players} {mode.lower()} players on {', '.join(sorted({c['platform'] for c in suitable}))}.")
        if f.get("check_access") and suitable:
            equipment = curated.get("equipment")
            if equipment is None:
                unknown.append("Equipment requirements are unknown")
            people = request.people
            def owns(p):
                owned = {v.casefold() for v in p.access.get("owned", [])}
                return str(record["id"]).casefold() in owned or record["title"].casefold() in owned
            def devices(p, platform_name):
                return platform_name in p.access.get("platforms", [])
            if mode == "Online":
                common = [c for c in suitable if all(devices(p, c["platform"]) for p in people)]
                if not common:
                    unknown.append("No shared online platform confirmed; cross-play is not assumed")
                for p in people:
                    if not owns(p):
                        unknown.append(f"{p.name}: game ownership is not confirmed")
                    if equipment and not set(equipment) <= set(p.access.get("equipment", [])):
                        unknown.append(f"{p.name}: required equipment is not confirmed")
            else:
                if not any(owns(p) and any(devices(p, c["platform"]) for c in suitable) for p in people):
                    unknown.append("A local host with the game and matching platform is not confirmed")
                available = {v for p in people for v in p.access.get("equipment", [])}
                if equipment and not set(equipment) <= available:
                    unknown.append("Shared equipment is not confirmed")
                controllers = sum(int(p.access.get("controllers", 0)) for p in people)
                required = curated.get("controllers_per_player")
                if required is None and fmt == "Video":
                    unknown.append("Controller requirement is unknown")
                elif required and controllers < players * required:
                    blocked.append("Not enough shared controllers")
        if f.get("mixed_experience"):
            if curated.get("mixed_experience") is None:
                unknown.append("Mixed-experience suitability is unknown")
            elif not curated["mixed_experience"]:
                blocked.append("Not suitable for the selected mixed-experience requirement")
        if f.get("recurring"):
            if curated.get("replayable") is None:
                unknown.append("Replayability is unknown")
            elif not curated["replayable"]:
                blocked.append("Not suitable for recurring play")
        if curated.get("source"):
            reasons.append(f"Play time and experience assessments: {curated['source']}.")

    if manual:
        reasons.append("Details are participant-provided, not independently verified.")
        if not record.get("confirmed_details"):
            unknown.append("A participant must explicitly confirm the supplied details")
    if record.get("source") == "Fictional demo":
        reasons.append("Fictional sample data; checks apply only to this demo scenario.")
    candidate = to_candidate(record, request)
    facts = dict(candidate.facts)
    if request.category_id == "play":
        facts.pop("Time", None)
        facts.pop("Players", None)
        facts["Commitment"] = f"{total} min incl. setup + teaching (estimate)" if total is not None else "Total time unknown"
        facts["Format"] = record.get("format", "Video")
    if record.get("year"):
        facts["Year"] = str(record["year"])
    facts["Source"] = record.get("source", "Unknown")
    optional_tags = tags | set(record.get("curated", {}).get("tags", []))
    if request.category_id == "play" and record.get("source") == "IGDB":
        if not any((c.get("coop_max") or 0) >= players for c in suitable):
            optional_tags.discard("Cooperative")
    candidate = replace(candidate, facts=facts, reasons=tuple(dict.fromkeys(reasons)),
                        matched_likes={p.id: tuple(v for v in p.likes if v in optional_tags) for p in request.people},
                        unknowns=tuple(dict.fromkeys(unknown)),
                        eligibility="excluded" if blocked else "unresolved" if unknown else "verified")
    return candidate, tuple(dict.fromkeys(blocked))


def match_records(records, request):
    verified, unresolved, failures = [], [], {}
    for record in records:
        candidate, blocked = evaluate(record, request)
        if blocked:
            for reason in blocked:
                failures[reason] = failures.get(reason, 0) + 1
        elif candidate.unknowns:
            unresolved.append(candidate)
        else:
            verified.append(candidate)
    conflicts = [f"{count} option(s): {reason}." for reason, count in sorted(failures.items())]
    # Counterfactuals are suggestions only. The original request is never changed.
    if not verified and records:
        adjustments = []
        if request.filters.get("max_duration"):
            adjustments.append(("Remove the shared time limit", replace(request, filters={**request.filters, "max_duration": 0})))
        for person in request.people:
            if person.avoids or person.requirements.get("max_duration"):
                changed = replace(person, avoids=(), requirements={**person.requirements, "max_duration": 0})
                adjustments.append((f"{person.name}: remove genre exclusions and personal time limit",
                                    replace(request, people=tuple(changed if p.id == person.id else p for p in request.people))))
        for label, adjusted in adjustments:
            count = sum(evaluate(r, adjusted)[0].eligibility == "verified" for r in records)
            if count:
                conflicts.append(f"Possible adjustment — {label}: unlocks {count} current option(s). Edit and save the relevant form to apply.")
    return verified, unresolved, conflicts
