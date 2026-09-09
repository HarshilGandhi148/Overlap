"""Do-only controls. Uses the shared group and voting state; no standalone app shell."""
from pathlib import Path
import streamlit as st
import streamlit.components.v1 as components
from core.contracts import CategorySearchError
from nearby.adapter import seed, service_for
from nearby.ingestion import load_area
from nearby.models import AppError, CATEGORIES, LocationContext, NYC

geolocation = components.declare_component('do_geolocation', path=str(Path(__file__).parent / 'location_component'))


def render_preferences(state, group, person_id):
    person = next(m for m in group.members if m['id'] == person_id)
    current = state.filters.get('do_people', {}).get(person_id, {})
    st.caption(f"Editing activity preferences for {person['name']}.")
    with st.form(f'do_preferences:{person_id}'):
        opinion = st.text_area('What would you like to do?', value=current.get('opinion', ''),
                               placeholder='A relaxed walk with some art to look at and somewhere to talk…',
                               max_chars=1000, key=f'widget:do:{person_id}:opinion')
        excludes = st.multiselect('Exclude categories', CATEGORIES, default=current.get('exclusions', ()),
                                   key=f'widget:do:{person_id}:exclude')
        if st.form_submit_button('Save preferences'):
            if not opinion.strip():
                st.warning(f'Write a little about what {person["name"]} wants to do.')
            else:
                profile = dict(opinion=opinion.strip(), exclusions=tuple(excludes))
                if current != profile:
                    state.invalidate()
                state.filters.setdefault('do_people', {})[person_id] = profile
                state.preferences[person_id] = {'likes': (), 'avoids': tuple(excludes)}
                st.rerun()
    saved = state.filters.get('do_people', {})
    missing = [m['name'] for m in group.members if not saved.get(m['id'], {}).get('opinion')]
    st.caption('Still needed: ' + ', '.join(missing) if missing else 'Everyone’s preferences are saved. Find your overlap below.')


def render_search_form(state, group, services):
    f = state.filters
    # Move existing browser sessions off the previous demo default once.
    if not st.session_state.get('ui_do_google_default_v1'):
        st.session_state.ui_do_google_default_v1 = True
        st.session_state.pop('widget:do:source', None)
        f['do_source'] = 'live'
        state.invalidate()
    sources = {'snapshot': 'Saved NYC demo · 50 real places', 'live': 'Google Places · load nearby activities'}
    with st.container(border=True):
        source = st.selectbox('Activity data', list(sources),
                              index=0 if f.get('do_source', 'live') == 'snapshot' else 1,
                              format_func=sources.get, key='widget:do:source')
        location = NYC
        if source == 'snapshot':
            st.caption('Starting in Midtown Manhattan. Saved OpenStreetMap data from September 8, 2026; prices and visit times may change.')
        else:
            method = st.radio('Starting point', ['Enter coordinates', 'Use browser location'],
                              key='widget:do:location_method')
            if method == 'Enter coordinates':
                left, right = st.columns(2)
                with left:
                    lat = st.number_input('Latitude', -90.0, 90.0, float(f.get('latitude') if f.get('latitude') is not None else NYC.latitude),
                                          format='%.5f', key='widget:do:latitude')
                with right:
                    lon = st.number_input('Longitude', -180.0, 180.0, float(f.get('longitude') if f.get('longitude') is not None else NYC.longitude),
                                          format='%.5f', key='widget:do:longitude')
                location = LocationContext(lat, lon)
            else:
                value = geolocation(key='widget:do:geolocation', default=None)
                location = None
                if value and not value.get('error'):
                    try:
                        location = LocationContext(float(value['latitude']), float(value['longitude']), 'browser')
                    except (KeyError, TypeError, ValueError):
                        st.warning('Could not read that location. Enter coordinates instead.')
                if location is None:
                    st.caption('Allow browser location access, or choose Enter coordinates.')
            st.caption('Loads up to 20 nearby Google Places with one request, cached for 30 minutes. Results match your group’s preferences, radius, and category exclusions.')
        radius = st.slider('Search radius (miles)', 1, 10, int(f.get('radius_miles', 5)), key='widget:do:radius')
        orders = ['Best group match', 'Nearest first']
        order = st.selectbox('Order results', orders, index=orders.index(f.get('order', orders[0])), key='widget:do:order')
        area_key = (source, location.key if location else None)
        if st.session_state.get('ui_do_area_key') != area_key:
            st.session_state.ui_do_area_key = area_key
            st.session_state.pop('ui_do_area', None)
            f.pop('candidate_ids', None)
            f.pop('area_note', None)
            state.invalidate()
        current = {k: f.get(k) for k in ('do_source', 'latitude', 'longitude', 'radius_miles', 'order')}
        updated = dict(do_source=source, latitude=location.latitude if location else None,
                       longitude=location.longitude if location else None, radius_miles=radius, order=order)
        if current != updated:
            f.update(updated)
            state.invalidate()
        label = 'Prepare / refresh NYC search' if source == 'snapshot' else 'Load / refresh nearby places'
        refresh = st.button(label, disabled=location is None)
        profiles = f.get('do_people', {})
        missing = [m['name'] for m in group.members if not profiles.get(m['id'], {}).get('opinion')]
        if missing:
            st.caption('Save activity preferences for everyone above before searching.')
        clicked = st.button('Find our overlap', type='primary', width='stretch', disabled=bool(missing) or location is None)
        if refresh or (clicked and source == 'live'):
            try:
                with st.spinner('Preparing nearby places and Typesense search…'):
                    if source == 'snapshot':
                        report = seed(services)
                        if report.failed:
                            raise AppError('Some places could not be indexed. Retry preparing the NYC search.')
                        st.success(f'{report.imported} NYC places ready in Typesense.')
                    else:
                        service = service_for(services)
                        previous = st.session_state.get('ui_do_area')
                        area = load_area(location, previous, force=refresh)
                        target = (services.settings, service.collection)
                        if area is not previous or not area.indexed_ids or area.index_failed or area.index_target != target:
                            area.indexed_ids, area.index_failed = service.index_places(area.activities)
                            area.index_target = target
                        if area.index_failed:
                            raise AppError('Some places could not be indexed. Refresh before searching; partial results were not used.')
                        st.session_state.ui_do_area = area
                        f['candidate_ids'] = area.indexed_ids
                        f['area_note'] = (area.warning if area.stale else 'Google Maps · nearby selection (up to 20 places)') + f' · {len(area.indexed_ids)} indexed / {area.total_discovered} discovered.'
                        if area.capped:
                            f['area_note'] += ' Limited to a balanced selection of 1,000 places.'
                        st.caption(f['area_note'])
                    if refresh:
                        state.invalidate()
            except (AppError, CategorySearchError) as exc:
                state.invalidate()
                st.error(str(exc))
                return False
        st.caption('Place data © OpenStreetMap contributors · ODbL · https://www.openstreetmap.org/copyright')
    return clicked
