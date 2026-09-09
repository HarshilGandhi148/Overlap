from html import escape
from urllib.parse import urlparse
import streamlit as st
from core.ranking import vote_status


def safe_url(url):
    return bool(url and urlparse(url).scheme in ("http", "https") and urlparse(url).netloc)


def render_card(candidate, state, people, index):
    with st.container(border=True):
        tag = " · ".join(candidate.tags[:3]) or "Your option"
        st.html(f'<div class="overlap-tag">{escape(tag)}</div><h3 class="overlap-card-title">{escape(candidate.title)}</h3>')
        st.caption(candidate.description)
        if candidate.facts:
            st.write(" · ".join(candidate.facts.values()))
        with st.expander("Why this fits"):
            for person in (() if candidate.category_id == 'do' else people):
                matches = candidate.matched_likes.get(person.id, ())
                if not person.likes:
                    st.write(f"{person.name}: no preference")
                elif matches:
                    st.write(f"{person.name}: {', '.join(matches)}")
                else:
                    st.write(f"{person.name}: fits requirements; no preferred tags matched")
            for reason in candidate.reasons:
                st.caption(reason)
        if safe_url(candidate.source_url):
            st.link_button("View original listing", candidate.source_url)
        selected = any(c.id == candidate.id for c in state.shortlist)
        if st.button("✓ Added to vote · Remove" if selected else "Add to vote",
                     key=f"shortlist:{candidate.category_id}:{candidate.id}", width="stretch",
                     disabled=not selected and len(state.shortlist) >= 3):
            state.toggle_shortlist(candidate)
            st.rerun()


def render_results(spec, state, group):
    if not state.searched:
        return
    if state.response:
        for warning in state.response.warnings:
            st.caption(warning)
        if state.response.unresolved:
            with st.expander(f'Needs confirmation · {len(state.response.unresolved)} options'):
                st.caption('These options cannot enter the vote until the required information is confirmed.')
                for candidate in state.response.unresolved[:20]:
                    st.markdown(f'**{candidate.title}**')
                    st.write(' · '.join(candidate.unknowns))
                if len(state.response.unresolved) > 20:
                    st.caption('Showing the first 20 options needing confirmation.')
        if state.response.conflicts:
            with st.expander('Why some options were excluded'):
                for conflict in state.response.conflicts:
                    st.caption(conflict)
    if not state.results:
        st.warning("No options fit this search. Adjust the query or explicitly change a group constraint.")
        return
    st.markdown(f"#### {len(state.results)} options for your group")
    st.caption(f"Pick up to 3 to vote on together. {len(state.shortlist)} of 3 selected.")
    if state.response:
        if state.response.search_time_ms is not None:
            st.caption(f"{state.response.engine} · server search: {state.response.search_time_ms} ms · choose up to 3")
        else:
            st.caption(f"{state.response.engine} · choose up to 3")
    people = group.people(state)
    columns = st.columns(2)
    for index, candidate in enumerate(state.results):
        with columns[index % 2]:
            render_card(candidate, state, people, index)


def render_shortlist(spec, state, group, person_id):
    if not state.shortlist:
        st.info("Add up to three options from the search results, then return here to vote.")
        return
    if state.chosen_id:
        chosen = next((c for c in state.shortlist if c.id == state.chosen_id), None)
        if chosen:
            st.success(f"Your group picked {chosen.title}.", icon="🎉")
    person = next(m for m in group.members if m["id"] == person_id)
    st.markdown(f"#### Voting as {person['name'].replace('*', '')}")
    st.caption("Choose Love, Okay, or Pass for every option, then save. Switch the name above for the next person.")
    with st.form(f"ballot:{spec.id}:{person_id}"):
        pending = {}
        for candidate in state.shortlist:
            options = [None, 2, 1, 0]
            current = state.votes.get(candidate.id, {}).get(person_id)
            pending[candidate.id] = st.radio(candidate.title, options, index=options.index(current),
                                             format_func=lambda v: {None: "Not voted", 2: "Love", 1: "Okay", 0: "Pass"}[v],
                                             horizontal=True,
                                             key=f"widget:vote:{spec.id}:{state.revision}:{candidate.id}:{person_id}")
        if st.form_submit_button("Save my votes", type="primary"):
            for candidate_id, vote in pending.items():
                ballot = state.votes.setdefault(candidate_id, {})
                if vote is None:
                    ballot.pop(person_id, None)
                else:
                    ballot[person_id] = vote
            state.chosen_id = None
            st.rerun()
    st.divider()
    st.markdown("#### The group’s verdict")
    st.caption("Love = 2 points · Okay = 1 · Pass = 0. Highest scores appear first. Everyone must vote before you confirm.")
    ids = [m["id"] for m in group.members]
    statuses = {c.id: vote_status(state.votes.get(c.id, {}), ids) for c in state.shortlist}
    all_complete = all(s[0] for s in statuses.values())
    for candidate in sorted(state.shortlist, key=lambda c: statuses[c.id][2], reverse=True):
        complete, consensus, points = statuses[candidate.id]
        votes = state.votes.get(candidate.id, {})
        with st.container(border=True):
            st.markdown(f"**{candidate.title}**")
            if not complete:
                missing = [m['name'] for m in group.members if m['id'] not in votes]
                st.caption("Waiting for: " + ", ".join(missing))
            elif not consensus:
                st.caption(f"{points} points · at least one person passed")
            else:
                st.caption(f"{points} points · everyone is okay with this")
            if st.button("Confirm this pick", key=f"confirm:{spec.id}:{candidate.id}",
                         disabled=not all_complete, width="stretch"):
                state.chosen_id = candidate.id
                st.session_state["celebrate_pick"] = True
                st.rerun()
    if all_complete and all(s[2] == 0 for s in statuses.values()):
        st.info("Every option scored 0. You can still choose one, or go back to find more options.")
