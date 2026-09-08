"""PERSON 4: replace this starter and data/play.json with your game work."""
from core.catalog import CatalogProvider
from core.contracts import CategorySpec, FilterField

SPEC = CategorySpec(
    "play", "Play", "What should we play?", "Match the game to the people around the table.",
    filter_fields=(FilterField("players", "Number of players", "number", 4, minimum=1, maximum=12),
                   FilterField("max_duration", "Maximum game time (minutes)", "number", 90, maximum=240, step=5)),
    like_options=("Cooperative", "Strategy", "Party", "Quick", "Creative"),
    avoid_options=("Cooperative", "Strategy", "Party", "Quick", "Creative"))
_provider = CatalogProvider(SPEC)


def get_spec():
    return SPEC


def search(request, services):
    return _provider.search(request, services)


def seed(services):
    return _provider.seed(services)
