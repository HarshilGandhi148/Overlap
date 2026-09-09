"""Play integration; preserves the shared category entrypoints."""
from core.media_catalog import MediaCatalog
from core.contracts import CategorySpec, FilterField

SPEC = CategorySpec(
    "play", "Play", "What should we play?", "Match the game to the people around the table.",
    filter_fields=(FilterField("players", "Number of players", "number", 4, minimum=1, maximum=12),
                   FilterField("max_duration", "Time including setup and teaching (minutes; 0 = no limit)", "number", 0, maximum=480, step=5),
                   FilterField("play_mode", "Play together", "select", "Local", choices=("Local", "Online")),
                   FilterField("platform", "Platform", "select", "Any", choices=("Any", "PC (Microsoft Windows)", "Nintendo Switch", "PlayStation 5", "Xbox Series X|S", "Tabletop", "Physical")),
                   FilterField("format", "Game format", "select", "Any", choices=("Any", "Video", "Tabletop", "Physical")),
                   FilterField("check_access", "Require confirmed ownership and equipment", "checkbox", False),
                   FilterField("mixed_experience", "Must suit mixed experience", "checkbox", False),
                   FilterField("recurring", "Must suit recurring play", "checkbox", False)),
    like_options=("Cooperative", "Competitive", "Strategy", "Party", "Quick", "Creative", "Relaxed", "Silly", "Immersive", "Easy to learn", "Skill", "Luck", "Familiar", "Replayable"),
    avoid_options=("Cooperative", "Strategy", "Party", "Quick", "Creative"))
_provider = MediaCatalog(SPEC)


def get_spec():
    return SPEC


def search(request, services):
    return _provider.search(request, services)


def seed(services):
    return _provider.seed(services)
