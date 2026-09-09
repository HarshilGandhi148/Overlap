"""Presentation and navigation only; category contracts and group rules stay in core."""
import logging
import streamlit as st
from core.state import GroupState


def init_state() -> GroupState:
    if "group" not in st.session_state:
        st.session_state.group = GroupState()
    return st.session_state.group


def navigate(page):
    st.session_state.ui_page = page
    st.session_state.ui_scroll_pending = True


def set_view(view):
    st.session_state.ui_view = view
    st.session_state.ui_scroll_pending = True


def remember_category():
    st.session_state.ui_category = st.session_state["widget:category"]
    st.session_state.ui_scroll_pending = True


def finish_navigation():
    if st.session_state.pop("ui_scroll_pending", False):
        version = st.session_state.get("ui_scroll_version", 0) + 1
        st.session_state.ui_scroll_version = version
        # Only our fixed UI script executes here; no names or category content is interpolated.
        st.html(f'''<script>
            // Navigation {version}: Streamlit otherwise retains the previous page's scroll offset.
            requestAnimationFrame(() => {{
                document.querySelector('[data-testid="stMain"]')?.scrollTo({{top: 0, behavior: 'instant'}});
            }});
        </script>''', unsafe_allow_javascript=True)


def remember_person(key):
    st.session_state.ui_person = st.session_state[key]


def reset_group():
    for key in list(st.session_state):
        if key.startswith(("widget:", "ui_")) or key in {"group", "active_person", "category", "decision_view"}:
            del st.session_state[key]
    st.session_state.ui_page = "names"
    st.session_state.ui_scroll_pending = True


def render_landing():
    with st.container(key="landing"):
        st.html('''<div class="hero">
            <div class="overlap-mark" aria-hidden="true"><span></span><span></span></div>
            <p class="wordmark">Overlap</p>
            <h1>Find your<br><span>common ground.</span></h1>
            <p class="hero-description">Different tastes. One great plan.<br>Find something everyone wants to eat, watch, play, or do.</p>
        </div>''')
        _, center, _ = st.columns([1, 1, 1])
        with center:
            st.button("Go →", type="primary", width="stretch", on_click=navigate, args=("names",))
        st.html('''<div class="hero-footer"><p>ONE GROUP. ONE SCREEN. NO MORE “I DON’T MIND.”</p>
            <div class="category-pills"><span>Eat</span><span>Do</span><span>Watch</span><span>Play</span><span>Anything</span></div></div>''')


def rename_member(person_id, key):
    name = st.session_state[key].strip()
    if name:
        member = next(m for m in st.session_state.group.members if m["id"] == person_id)
        member["name"] = name


def remove_member(person_id):
    group = st.session_state.group
    group.remove(person_id)
    if st.session_state.get("ui_person") == person_id:
        st.session_state.ui_person = group.members[0]["id"]


def render_names(group):
    with st.container(key="names_page"):
        st.button("← Home", on_click=navigate, args=("home",), type="tertiary")
        st.html('<p class="eyebrow">LET’S GET EVERYONE IN</p><h1 class="page-title">Who’s joining?</h1>')
        st.caption("Add your names or nicknames. Everyone takes turns on this screen.")
        with st.container(border=True):
            st.markdown("#### Your group")
            valid = True
            for index, member in enumerate(group.members):
                field, remove = st.columns([5, 1], vertical_alignment="bottom")
                key = f"widget:name:{member['id']}"
                with field:
                    value = st.text_input(f"Person {index + 1}", value=member["name"], max_chars=40,
                                          key=key, on_change=rename_member, args=(member["id"], key))
                    valid = valid and bool(value.strip())
                with remove:
                    st.button("Remove", key=f"remove:{member['id']}", disabled=len(group.members) <= 1,
                              on_click=remove_member, args=(member["id"],), width="stretch")
            with st.form("add_member", clear_on_submit=True, border=False):
                field, add = st.columns([5, 1], vertical_alignment="bottom")
                with field:
                    name = st.text_input("Add a person", placeholder="Someone else joining?", max_chars=40)
                with add:
                    submitted = st.form_submit_button("Add", width="stretch", disabled=len(group.members) >= 12)
                if submitted:
                    try:
                        st.session_state.ui_person = group.add(name)
                        st.rerun()
                    except ValueError as exc:
                        st.warning(str(exc))
        if not valid:
            st.caption("Give each person a name to continue.")
        st.button("Continue →", type="primary", width="stretch", disabled=not valid,
                  on_click=navigate, args=("app",))
        st.caption("You can come back with Edit names at any time. Adding or removing people resets existing votes.")


def render_header(group):
    brand, names, settings = st.columns([5, 2, 1], vertical_alignment="center")
    with brand:
        st.html('<div class="app-brand">◎ Overlap <span>One group. One good plan.</span></div>')
    with names:
        st.button(f"Edit names · {len(group.members)}", on_click=navigate, args=("names",), width="stretch")
    return settings


def render_steps(state):
    view = st.session_state.get("ui_view", "Preferences")
    with st.container(key="decision_steps"):
        discover, vote = st.columns(2)
        with discover:
            st.button("1 · Discover", type="primary" if view == "Preferences" else "secondary",
                      on_click=set_view, args=("Preferences",), width="stretch")
        with vote:
            st.button(f"2 · Vote ({len(state.shortlist)})", type="primary" if view == "Shortlist" else "secondary",
                      on_click=set_view, args=("Shortlist",), width="stretch")
    return view


def render_person_picker(group, context):
    ids = [m["id"] for m in group.members]
    names = {m["id"]: m["name"] for m in group.members}
    active = st.session_state.get("ui_person", ids[0])
    if active not in ids:
        active = ids[0]
    key = f"widget:person:{context}"
    # Widget values may be cleaned up between pages; the durable UI selection survives.
    st.session_state[key] = active
    st.selectbox("Whose turn?" if context == "vote" else "Preferences for", ids,
                 format_func=lambda i: names[i], key=key,
                 on_change=remember_person, args=(key,))
    st.session_state.ui_person = active
    return active


def vote_button(state, key):
    st.button(f"Vote on {len(state.shortlist)} option{'s' if len(state.shortlist) != 1 else ''} →",
              type="primary", width="stretch", key=key, on_click=set_view, args=("Shortlist",))


def render_developer_settings(group, services):
    default = "typesense" if services.settings.api_key else "sample"
    mode = st.session_state.get("ui_engine", default)
    with st.popover("Settings", width="stretch"):
        st.markdown("#### Developer settings")
        st.caption("Changing the search engine clears results and votes.")
        def change_engine():
            st.session_state.ui_engine = st.session_state["widget:search_engine"]
            group.invalidate_all()
        st.radio("Search engine", ["typesense", "sample"], index=0 if mode == "typesense" else 1,
                 format_func=lambda m: "Typesense" if m == "typesense" else "Sample preview (offline)",
                 key="widget:search_engine", on_change=change_engine)
        if st.button("Check search connection"):
            try:
                if services.health():
                    st.success("Typesense is ready.")
                else:
                    st.warning("Typesense is not ready yet.")
            except Exception:
                logging.exception("Health check failed")
                st.error("Cannot reach Typesense. Check .env and the local server.")
        st.divider()
        st.button("Start a new decision", on_click=reset_group, width="stretch")
    return mode
