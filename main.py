"""Person 1's entrypoint. Category owners should not edit this file."""
from pathlib import Path
import logging
import streamlit as st
from core.contracts import CategorySearchError, SearchRequest, validate_response
from core.ranking import rank_candidates
from core.registry import load_categories
from core.services import AppServices, Settings
from ui.forms import render_preferences, render_search_form
from ui.results import render_results, render_shortlist
from ui.shell import (init_state, render_developer_settings, render_landing, render_names,
                      render_header, render_steps, render_person_picker, remember_category,
                      vote_button, set_view, finish_navigation)

st.set_page_config(page_title="Overlap · Find your common ground", page_icon="◎", layout="wide")
st.set_option("client.toolbarMode", "viewer")
st.html((Path(__file__).parent / "ui" / "theme.css").read_text())


@st.cache_resource
def get_services(settings: Settings) -> AppServices:
    return AppServices(settings)


def main():
    group = init_state()
    if st.session_state.pop("celebrate_pick", False):
        from ui.celebration import confetti
        confetti()
    page = st.session_state.get("ui_page", "home")
    if page == "home":
        render_landing()
        return
    if page == "names":
        render_names(group)
        return
    try:
        shared_services = get_services(Settings.from_env())
    except CategorySearchError as exc:
        st.error(str(exc))
        st.stop()
    settings_column = render_header(group)
    with settings_column:
        mode = render_developer_settings(group, shared_services)
    # The client is cached, but a category never changes the shared service mode.
    services = AppServices(shared_services.settings, mode, shared_services._client)
    ready, unavailable = load_categories()
    if not ready:
        st.error("No categories are ready. Check the shared module contract in TEAM_HANDOFF.md.")
        st.stop()
    st.divider()
    selected = st.session_state.get("ui_category", next(iter(ready)))
    if selected not in ready:
        selected = next(iter(ready))
    category_id = st.segmented_control("What are we deciding?", list(ready),
                                       format_func=lambda key: ready[key][0].label,
                                       default=selected, required=True, key="widget:category",
                                       on_change=remember_category, width="stretch") or selected
    st.session_state.ui_category = category_id
    if category_id not in ready:
        category_id = next(iter(ready))
    spec, module = ready[category_id]
    state = group.category(spec)
    decision_view = render_steps(state)
    st.title(spec.title if decision_view == "Preferences" else "Let’s vote.")
    st.caption(spec.description if decision_view == "Preferences" else
               "Pass the screen around. Pick the option everyone can get behind.")
    if mode == 'sample' and spec.id != 'do' and not spec.custom:
        st.html('<p class="sample-note">Sample catalog · Fictional listings for the demo.</p>')
    if unavailable:
        st.caption("Not integrated yet: " + ", ".join(key.title() for key in unavailable))
    if decision_view == "Shortlist":
        if not state.shortlist:
            st.info("Choose up to 3 options in Discover, then come here to vote.")
            st.button("← Find options", on_click=set_view, args=("Preferences",))
            return
        active_person = render_person_picker(group, "vote")
        render_shortlist(spec, state, group, active_person)
        return
    # Save member preferences first, then run a query using the saved group inputs.
    if category_id == "do":
        from nearby.integration_ui import render_preferences as do_preferences, render_search_form as do_search_form
        profiles = state.filters.get('do_people', {})
        saved = sum(bool(profiles.get(m['id'], {}).get('opinion')) for m in group.members)
        with st.expander(f"Activity preferences · {saved}/{len(group.members)} saved · required", expanded=saved < len(group.members)):
            active_person = render_person_picker(group, "preferences")
            do_preferences(state, group, active_person)
        submitted = do_search_form(state, group, services)
    elif not spec.custom:
        saved = sum(m["id"] in state.preferences for m in group.members)
        with st.expander(f"Group preferences · {saved}/{len(group.members)} saved · optional"):
            active_person = render_person_picker(group, "preferences")
            render_preferences(spec, state, group, active_person)
        if spec.id == 'watch':
            from ui.media import render_suggestions
            render_suggestions(spec, state, services)
        submitted = render_search_form(spec, state)
        if spec.id == 'play':
            from ui.media import render_suggestions
            render_suggestions(spec, state, services)
    else:
        submitted = render_search_form(spec, state)
    if submitted or (state.needs_search and spec.id in ('watch', 'play')):
        state.needs_search = False
        custom_options = tuple(s.strip() for s in state.custom_text.splitlines() if s.strip())
        if spec.custom and (not custom_options or len(custom_options) > 30):
            st.warning("Enter between 1 and 30 options, one per line.")
        else:
            request = SearchRequest(spec.id, group.people(state), state.query, dict(state.filters),
                                    custom_options=custom_options, suggestions=tuple(state.suggestions))
            try:
                with st.spinner("Finding your common ground…"):
                    response = module.search(request, services)
                    validate_response(response, request)
                    state.results = rank_candidates(response.candidates, request.people)
                    state.response, state.searched = response, True
                    # Reuse the initialized client on subsequent reruns.
                    if services._client is not None:
                        shared_services._client = services._client
            except CategorySearchError as exc:
                state.invalidate()
                st.error(str(exc))
            except Exception:
                logging.exception("Category search failed: %s", spec.id)
                state.invalidate()
                st.error("This category returned an unexpected error. Check its module and try again.")
    render_results(spec, state, group)
    if state.shortlist:
        vote_button(state, "vote_bottom")


if __name__ == "__main__":
    main()
    finish_navigation()
