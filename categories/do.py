"""PERSON 3: replace this starter and data/do.json with your activity work."""
from core.catalog import CatalogProvider
from core.contracts import CategorySpec, FilterField

SPEC = CategorySpec(
    "do", "Do", "What should we do?", "Find a plan that matches the group’s energy.",
    filter_fields=(FilterField("budget", "Budget per person ($)", "number", 40, maximum=200),
                   FilterField("max_duration", "Time available (minutes)", "number", 120, maximum=360, step=15),
                   FilterField("setting", "Setting", "select", "Any", ("Any", "Indoors", "Outdoors"))),
    like_options=("Creative", "Social", "Active", "Relaxed", "Outdoors"),
    avoid_options=("Creative", "Social", "Active", "Relaxed", "Outdoors"))
_provider = CatalogProvider(SPEC)


def get_spec():
    return SPEC


def search(request, services):
    return _provider.search(request, services)


def seed(services):
    return _provider.seed(services)
