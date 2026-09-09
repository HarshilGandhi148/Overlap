"""Watch integration; preserves the shared category entrypoints."""
from core.media_catalog import MediaCatalog
from core.contracts import CategorySpec, FilterField

SPEC = CategorySpec(
    "watch", "Watch", "What should we watch?", "Spend movie night watching something.",
    filter_fields=(FilterField("max_duration", "Maximum runtime (minutes; 0 = no limit)", "number", 150, maximum=300, step=5),),
    like_options=("Comedy", "Adventure", "Mystery", "Drama", "Animation", "Sci-fi", "Horror", "Lighthearted", "Tense", "Thoughtful"),
    avoid_options=("Comedy", "Adventure", "Mystery", "Drama", "Animation", "Sci-fi", "Horror"))
_provider = MediaCatalog(SPEC)


def get_spec():
    return SPEC


def search(request, services):
    return _provider.search(request, services)


def seed(services):
    return _provider.seed(services)
