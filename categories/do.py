"""Person 3's nearby activity search, adapted to Overlap's shared category contract."""
from core.contracts import CategorySpec
from nearby.adapter import search, seed

SPEC = CategorySpec(
    "do", "Do", "What should we do?",
    "Tell us what everyone has in mind. Find a nearby plan everyone can get behind.",
    is_sample=False,
)


def get_spec():
    return SPEC
