from dataclasses import dataclass, field, asdict
from math import radians, sin, cos, atan2, sqrt, isfinite

MILES_TO_METERS = 1609.344
AREA_RADIUS_MILES = 10
MAX_PLACES = 1000
CATEGORIES = ('park', 'museum', 'gallery', 'attraction', 'playground', 'entertainment', 'sports', 'cafe', 'restaurant')

class AppError(Exception):
    """Safe-to-display operational error, without credentials or user text."""

@dataclass(frozen=True)
class LocationContext:
    latitude: float
    longitude: float
    mode: str = 'manual'

    def __post_init__(self):
        if not isfinite(self.latitude) or not isfinite(self.longitude) or not -90 <= self.latitude <= 90 or not -180 <= self.longitude <= 180:
            raise ValueError('Enter valid latitude and longitude.')

    @property
    def key(self):
        return (self.latitude, self.longitude)

NYC = LocationContext(40.7549, -73.9840, 'demo')

@dataclass(frozen=True)
class ParticipantPreferences:
    id: str
    name: str
    opinion: str
    max_minutes: int = 120
    max_cost: float = 35
    exclusions: tuple[str, ...] = ()
    wheelchair: bool = False

    def __post_init__(self):
        if not self.id or not self.name.strip() or not self.opinion.strip():
            raise ValueError('Each person needs a name and written activity preferences.')
        if len(self.opinion) > 1000 or len(self.name) > 40:
            raise ValueError('Keep names under 40 characters and opinions under 1,000 characters.')
        if not 1 <= self.max_minutes <= 1440 or not isfinite(self.max_cost) or not 0 <= self.max_cost <= 10000:
            raise ValueError('Enter a positive time limit and a nonnegative budget.')
        if not set(self.exclusions) <= set(CATEGORIES):
            raise ValueError('Choose exclusions from the supported categories.')

@dataclass(frozen=True)
class OutingRequest:
    location: LocationContext
    radius_miles: float
    people: tuple[ParticipantPreferences, ...]
    enforce_metadata_limits: bool = True  # Legacy standalone callers; shared Do disables these.

    def __post_init__(self):
        if not 1 <= len(self.people) <= 12 or len({p.id for p in self.people}) != len(self.people):
            raise ValueError('Add between 1 and 12 people with unique identifiers.')
        if not 1 <= self.radius_miles <= 10:
            raise ValueError('Choose a radius between 1 and 10 miles.')

    @property
    def time_limit(self): return min(p.max_minutes for p in self.people)
    @property
    def budget_limit(self): return min(p.max_cost for p in self.people)
    @property
    def exclusions(self): return sorted({c for p in self.people for c in p.exclusions})

@dataclass
class Activity:
    id: str
    name: str
    location: list[float]
    categories: list[str]
    description: str = ''
    tags: list[str] = field(default_factory=list)
    address: str = ''
    website: str = ''
    opening_hours: str = ''
    wheelchair: str = 'unknown'
    fee: str = 'unknown'
    source_url: str = ''
    fetched_at: int = 0
    cost_min: float | None = None
    cost_max: float | None = None
    duration_min: int | None = None
    duration_max: int | None = None
    cost_basis: str = 'unknown'
    duration_basis: str = 'unknown'
    metadata_sources: list[str] = field(default_factory=list)
    verified_at: str = ''
    activity_scope: str = ''
    aliases: list[str] = field(default_factory=list)

    def document(self):
        doc = {k: v for k, v in asdict(self).items() if v is not None}
        doc['has_cost'] = self.cost_max is not None
        doc['has_duration'] = self.duration_max is not None
        doc['search_text'] = '. '.join(filter(None, [self.name, self.description, ', '.join(self.categories), ', '.join(self.tags)]))
        return doc

@dataclass
class AreaBatch:
    location_key: tuple[float, float]
    activities: list[Activity]
    loaded_at: float
    total_discovered: int
    capped: bool = False
    stale: bool = False
    warning: str = ''
    indexed_ids: list[str] = field(default_factory=list)
    index_failed: int = 0
    index_target: str = ''
    load_seconds: float = 0

@dataclass
class RankedActivity:
    document: dict
    score: float
    distance_miles: float
    individual_scores: dict[str, float]
    components: dict[str, float]

@dataclass
class RecommendationResponse:
    ranked: list[RankedActivity]
    nearest: list[RankedActivity]
    eligible_count: int
    geographic_count: int
    missing_metadata_count: int
    query_seconds: float
    indexed_count: int


def distance_miles(a, b):
    """Distance scoring only. Geographic eligibility is enforced by Typesense."""
    la, lo, lb, lob = map(radians, (*a, *b))
    h = sin((lb-la)/2)**2 + cos(la)*cos(lb)*sin((lob-lo)/2)**2
    return 3958.7613 * 2 * atan2(sqrt(min(1, h)), sqrt(max(0, 1-h)))
