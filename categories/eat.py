"""PERSON 2: replace this starter and data/eat.json with your restaurant work."""
from core.catalog import CatalogProvider
from core.contracts import CategorySpec, FilterField

SPEC = CategorySpec(
    "eat", "Eat", "Where should we eat?", "A place the whole table can get behind.",
    filter_fields=(FilterField("budget", "Budget per person ($)", "number", 30, minimum=0, maximum=200),
                   FilterField("city", "City (optional)", "text", ""),
                   FilterField("dietary_options", "Required menu options", "multiselect", [],
                               ("Vegetarian", "Vegan"), help="Published menu options are not a guarantee of allergen safety.")),
    like_options=("Mexican", "Italian", "Japanese", "Indian", "American", "Mediterranean"),
    avoid_options=("Mexican", "Italian", "Japanese", "Indian", "American", "Mediterranean"))
_provider = CatalogProvider(SPEC)


def get_spec():
    return SPEC


def search(request, services):
    return _provider.search(request, services)


def seed(services):
    return _provider.seed(services)
