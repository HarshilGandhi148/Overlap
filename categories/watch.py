"""PERSON 4: replace this starter and data/watch.json with your movie work."""
from core.catalog import CatalogProvider
from core.contracts import CategorySpec, FilterField

SPEC = CategorySpec(
    "watch", "Watch", "What should we watch?", "Spend movie night watching something.",
    filter_fields=(FilterField("max_duration", "Maximum runtime (minutes)", "number", 150, maximum=300, step=5),),
    like_options=("Comedy", "Adventure", "Mystery", "Drama", "Animation", "Sci-fi", "Horror"),
    avoid_options=("Comedy", "Adventure", "Mystery", "Drama", "Animation", "Sci-fi", "Horror"))
_provider = CatalogProvider(SPEC)


def get_spec():
    return SPEC


def search(request, services):
    return _provider.search(request, services)


def seed(services):
    return _provider.seed(services)
