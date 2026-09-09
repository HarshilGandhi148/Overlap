"""Watch and Play controls embedded in the existing shared forms and shell."""
from uuid import uuid4
import streamlit as st


PLATFORMS = ("PC (Microsoft Windows)", "Nintendo Switch", "PlayStation 5", "Xbox Series X|S", "Tabletop", "Physical")


def lines(value):
    return [s.strip() for s in value.splitlines() if s.strip()]


def member_requirements(spec, current, person_id):
    req, access = dict(current.get("requirements", {})), dict(current.get("access", {}))
    prefix = f"widget:{spec.id}:{person_id}"
    anything = st.checkbox("I’m down for anything", value=req.get("anything", False), key=f"{prefix}:anything",
                           help="Skips optional likes. Your requirements and exclusions still apply.")
    req["anything"] = anything
    if spec.id == "watch":
        req["max_duration"] = st.number_input("My time limit (minutes; 0 = no limit)", min_value=0, max_value=600,
                                              value=int(req.get("max_duration", 0)), step=5, key=f"{prefix}:time")
        req["watched"] = lines(st.text_area("Already watched — exclude these titles or IMDb IDs", value="\n".join(req.get("watched", [])),
                                             key=f"{prefix}:watched", height=80))
        st.caption("Genre exclusions do not verify detailed sensitive content. Streaming availability is outside this demo.")
    else:
        with st.expander("Personal limits & equipment · optional", expanded=bool(req.get("max_duration") or any(access.values()))):
            req["max_duration"] = st.number_input("My time limit (minutes; 0 = no limit)", min_value=0, max_value=600,
                                                  value=int(req.get("max_duration", 0)), step=5, key=f"{prefix}:time")
            access["platforms"] = st.multiselect("Available platforms", PLATFORMS, default=access.get("platforms", []), key=f"{prefix}:platforms")
            access["owned"] = lines(st.text_area("Games I own — titles or catalog IDs, one per line", value="\n".join(access.get("owned", [])), key=f"{prefix}:owned"))
            access["equipment"] = lines(st.text_area("Equipment — one item per line", value="\n".join(access.get("equipment", [])), key=f"{prefix}:equipment"))
            access["controllers"] = st.number_input("Available controllers", min_value=0, max_value=12, value=int(access.get("controllers", 0)), key=f"{prefix}:controllers")
    return req, access, anything


def render_suggestions(spec, state, services):
    with st.expander("Add an option of your own"):
        from core.media_catalog import MediaCatalog
        from core.contracts import CategorySearchError
        lookup_key = f"widget:{spec.id}:lookup_results"
        with st.form(f"catalog-lookup:{spec.id}"):
            query = st.text_input("Find a catalog title", max_chars=150)
            if st.form_submit_button("Search catalog titles"):
                try:
                    st.session_state[lookup_key] = MediaCatalog(spec).lookup(query, services)
                    if not st.session_state[lookup_key]:
                        st.info("No imported title found. Add a custom suggestion below or import it first.")
                except CategorySearchError as exc:
                    st.error(str(exc))
        for record in st.session_state.get(lookup_key, []):
            if st.button(f"Suggest {record['title']}", key=f"suggest-catalog:{spec.id}:{record['id']}"):
                if not any(r["id"] == record["id"] for r in state.suggestions):
                    state.suggestions.append(record)
                    state.invalidate()
                    state.needs_search = True
                    st.rerun()
        st.caption("Suggestions are checked against the same requirements. Details you enter are labeled participant-provided.")
        with st.form(f"suggestion:{spec.id}", clear_on_submit=True):
            title = st.text_input("Suggestion title", max_chars=150)
            description = st.text_area("Optional description", max_chars=1500)
            duration = st.number_input("Estimated runtime / play time (minutes; 0 = unknown)", min_value=0, max_value=600)
            tags = st.multiselect("Known genres / style", spec.like_options)
            genres_known = st.checkbox("Genre list is complete enough to check exclusions")
            record = {"source": "Participant-provided", "description": description, "tags": tags, "genres_known": genres_known}
            if spec.id == "play":
                fmt = st.selectbox("Suggestion format", ["Video", "Tabletop", "Physical"])
                platform = st.selectbox("Suggestion platform", PLATFORMS)
                mode = st.selectbox("Suggestion play mode", ["Local", "Online"])
                minimum = st.number_input("Minimum players", min_value=1, max_value=12, value=2)
                maximum = st.number_input("Maximum players", min_value=1, max_value=12, value=4)
                setup = st.number_input("Setup minutes", min_value=0, max_value=120)
                teaching = st.number_input("Teaching minutes", min_value=0, max_value=120)
                equipment = lines(st.text_area("Required equipment — one item per line"))
                controllers = st.number_input("Controllers per player", min_value=0, max_value=2, value=1)
                mixed = st.checkbox("Suitable for mixed experience")
                replay = st.checkbox("Suitable for recurring play")
                record.update(format=fmt, multiplayer=[{"platform": platform, "mode": mode, "min_players": minimum, "max_players": maximum}],
                              curated={"session_max": duration or None, "setup_minutes": setup, "teaching_minutes": teaching,
                                       "equipment": equipment, "controllers_per_player": controllers if fmt == "Video" else 0,
                                       "mixed_experience": mixed, "replayable": replay, "source": "Participant estimate"})
            record["confirmed_details"] = st.checkbox("I confirm the supplied details for this decision")
            if st.form_submit_button("Add suggestion"):
                if not title.strip():
                    st.warning("Enter a title.")
                elif spec.id == "play" and minimum > maximum:
                    st.warning("Minimum players cannot exceed maximum players.")
                elif len(state.suggestions) >= 30:
                    st.warning("Keep at most 30 suggestions in one decision.")
                else:
                    record.update(id=f"manual-{uuid4().hex}", title=title.strip())
                    if duration:
                        record["duration"] = duration
                    state.suggestions.append(record)
                    state.invalidate()
                    state.needs_search = True
                    st.rerun()
        for record in list(state.suggestions):
            left, right = st.columns([3, 1])
            left.write(record["title"])
            if right.button("Remove", key=f"remove-suggestion:{record['id']}"):
                state.suggestions.remove(record)
                state.invalidate()
                state.needs_search = True
                st.rerun()
