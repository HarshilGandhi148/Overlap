import logging
import streamlit as st
from core.state import GroupState


def init_state() -> GroupState:
    if "group" not in st.session_state:
        st.session_state.group = GroupState()
    return st.session_state.group


def reset_group():
    for key in list(st.session_state):
        if key.startswith("widget:") or key in {"group", "active_person", "category", "decision_view"}:
            del st.session_state[key]


def remove_member():
    group = st.session_state.group
    group.remove(st.session_state.active_person)
    st.session_state.active_person = group.members[0]["id"]


def render_sidebar(group: GroupState):
    with st.sidebar:
        st.markdown("## ◎ Overlap")
        st.caption("One group. One good plan.")
        st.divider()
        st.markdown("#### Your group")
        with st.form("add_member", clear_on_submit=True):
            name = st.text_input("Add a person", max_chars=40, placeholder="Their name")
            if st.form_submit_button("Add person", width="stretch"):
                try:
                    person_id = group.add(name)
                    st.session_state.active_person = person_id
                    st.rerun()
                except ValueError as exc:
                    st.warning(str(exc))
        ids = [m["id"] for m in group.members]
        names = {m["id"]: m["name"] for m in group.members}
        if st.session_state.get("active_person") not in ids:
            st.session_state.active_person = ids[0]
        active = st.radio("Editing preferences for", ids, format_func=lambda i: names[i], key="active_person")
        with st.expander("Edit this person"):
            with st.form("rename_member"):
                new_name = st.text_input("Display name", value=names[active], max_chars=40,
                                         key=f"widget:rename:{active}")
                if st.form_submit_button("Save name"):
                    if new_name.strip():
                        next(m for m in group.members if m["id"] == active)["name"] = new_name.strip()
                        st.rerun()
                    else:
                        st.warning("Enter a name.")
            st.button("Remove person", disabled=len(ids) <= 1, on_click=remove_member)
        st.caption("Everyone takes turns on this screen. No sign-in needed.")
        st.divider()
        st.button("Start a new decision", on_click=reset_group, width="stretch")
    return active


def render_developer_settings(group, services):
    with st.sidebar.expander("Developer settings"):
        st.caption("Changes here clear old search results and votes.")
        default = "typesense" if services.settings.api_key else "sample"
        mode = st.radio("Search engine", ["typesense", "sample"],
                        index=0 if default == "typesense" else 1,
                        format_func=lambda m: "Typesense" if m == "typesense" else "Sample preview (offline)",
                        key="search_engine", on_change=group.invalidate_all)
        st.caption(f"Server: {services.settings.protocol}://{services.settings.host}:{services.settings.port}")
        if st.button("Check search connection"):
            try:
                if services.health():
                    st.success("Typesense is ready.")
                else:
                    st.warning("Typesense is not ready yet.")
            except Exception:
                logging.exception("Health check failed")
                st.error("Cannot reach Typesense. Check .env and the local server.")
        st.caption("Keys are read from .env and never displayed. Original catalogs live in data/.")
        return mode
