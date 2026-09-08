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
from ui.shell import init_state, render_developer_settings, render_sidebar

st.set_page_config(page_title="Overlap · Find your common ground", page_icon="◎", layout="wide")
st.html((Path(__file__).parent / "ui" / "theme.css").read_text())


@st.cache_resource
def get_services(settings: Settings) -> AppServices:
    return AppServices(settings)


def main():
    group = init_state()
    active_person = render_sidebar(group)
    try:
        shared_services = get_services(Settings.from_env())
    except CategorySearchError as exc:
        st.error(str(exc))
        st.stop()
    mode = render_developer_settings(group, shared_services)
    # The client is cached, but a category never changes the shared service mode.
    services = AppServices(shared_services.settings, mode, shared_services._client)
    ready, unavailable = load_categories()
    if not ready:
        st.error("No categories are ready. Check the shared module contract in TEAM_HANDOFF.md.")
        st.stop()
    nav, view = st.columns([3, 1])
    with nav:
        category_id = st.segmented_control("What are we deciding?", list(ready),
                                           format_func=lambda key: ready[key][0].label,
                                           default=next(iter(ready)), required=True, key="category",
                                           width="stretch") or next(iter(ready))
    if category_id not in ready:
        category_id = next(iter(ready))
    spec, module = ready[category_id]
    state = group.category(spec)
    with view:
        decision_view = st.segmented_control("View", ["Preferences", "Shortlist"], default="Preferences",
                                             required=True, key="decision_view", width="stretch")
    st.title(spec.title if decision_view == "Preferences" else "Find your common ground")
    st.caption(spec.description if decision_view == "Preferences" else
               "Take turns voting, then make a choice everyone can accept.")
    if spec.is_sample:
        st.info("Starter catalog: these are fictional examples. Your teammate will replace them with real listings.", icon="🧪")
    if unavailable:
        st.caption("Not integrated yet: " + ", ".join(key.title() for key in unavailable))
    if decision_view == "Shortlist":
        render_shortlist(spec, state, group, active_person)
        return
    # Save member preferences first, then run a query using the saved group inputs.
    render_preferences(spec, state, group, active_person)
    submitted = render_search_form(spec, state)
    if submitted:
        custom_options = tuple(s.strip() for s in state.custom_text.splitlines() if s.strip())
        if spec.custom and (not custom_options or len(custom_options) > 30):
            st.warning("Enter between 1 and 30 options, one per line.")
        else:
            request = SearchRequest(spec.id, group.people(state), state.query, dict(state.filters),
                                    custom_options=custom_options)
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
        st.caption(f"{len(state.shortlist)} shortlisted · open Shortlist above to vote")


if __name__ == "__main__":
    main()
