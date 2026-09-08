import streamlit as st
from core.contracts import FilterField


def render_field(field: FilterField, value, key: str):
    common = {"key": key, "help": field.help}
    if field.kind == "number":
        return st.number_input(field.label, min_value=field.minimum, max_value=field.maximum,
                               value=int(value if value is not None else field.default), step=field.step, **common)
    if field.kind == "select":
        return st.selectbox(field.label, field.choices,
                            index=field.choices.index(value) if value in field.choices else 0, **common)
    if field.kind == "multiselect":
        return st.multiselect(field.label, field.choices, default=value or [], **common)
    if field.kind == "checkbox":
        return st.checkbox(field.label, value=bool(value), **common)
    if field.kind == "text":
        return st.text_input(field.label, value=value or "", **common)
    raise ValueError(f"Unsupported field type: {field.kind}")


def render_search_form(spec, state):
    submitted = False
    with st.form(f"search:{spec.id}"):
        if spec.custom:
            custom_text = st.text_area("Your options — one per line", value=state.custom_text,
                                      placeholder="Cook dinner together\nOrder takeout\nGo for a walk",
                                      height=150, max_chars=5000, key=f"widget:{spec.id}:custom")
            query, filters = "", {}
        else:
            query = st.text_input("What is your group looking for?", value=state.query,
                                  placeholder="Search a name, interest, cuisine, or mood…",
                                  key=f"widget:{spec.id}:query", max_chars=300)
            filters = {}
            columns = st.columns(min(len(spec.filter_fields), 3)) if spec.filter_fields else []
            for index, field in enumerate(spec.filter_fields):
                with columns[index % len(columns)]:
                    filters[field.key] = render_field(field, state.filters.get(field.key, field.default),
                                                     f"widget:{spec.id}:filter:{field.key}")
            custom_text = ""
        if st.form_submit_button("Show our options" if spec.custom else "Find our overlap",
                                 type="primary", width="stretch"):
            if (query, filters, custom_text) != (state.query, state.filters, state.custom_text):
                state.query, state.filters, state.custom_text = query, filters, custom_text
                state.invalidate()
            submitted = True
    return submitted


def render_preferences(spec, state, group, person_id):
    if spec.custom:
        return
    person = next(m for m in group.members if m["id"] == person_id)
    current = state.preferences.get(person_id, {"likes": (), "avoids": ()})
    with st.container(border=True):
        name = person['name'].replace('*', '')
        st.markdown("#### Your preferences" if name == "You" else f"#### {name}’s preferences")
        st.caption("Likes influence ranking. Exclusions apply to every result. Leave likes empty for no preference.")
        with st.form(f"preferences:{spec.id}:{person_id}"):
            left, right = st.columns(2)
            with left:
                likes = st.multiselect("Would like", spec.like_options, default=list(current['likes']),
                                       key=f"widget:{spec.id}:{person_id}:likes")
            with right:
                avoids = st.multiselect("Exclude", spec.avoid_options, default=list(current['avoids']),
                                        key=f"widget:{spec.id}:{person_id}:avoids")
            if st.form_submit_button("Save preferences"):
                overlap = set(likes) & set(avoids)
                if overlap:
                    st.warning("Choose either like or exclude for: " + ", ".join(sorted(overlap)))
                else:
                    state.set_preferences(person_id, likes, avoids)
                    st.rerun()
        saved = sum(m["id"] in state.preferences for m in group.members)
        st.caption(f"{saved} / {len(group.members)} people have saved preferences. Others are treated as neutral.")
