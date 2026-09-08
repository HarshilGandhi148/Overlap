"""The stable boundary between the shared UI and each teammate's category."""
from dataclasses import dataclass, field
from typing import Any, Literal


class CategorySearchError(Exception):
    """An actionable, safe-to-display search or setup error."""


@dataclass(frozen=True)
class FilterField:
    key: str
    label: str
    kind: Literal["text", "number", "select", "multiselect", "checkbox"]
    default: Any = None
    choices: tuple[str, ...] = ()
    minimum: int = 0
    maximum: int = 100
    step: int = 1
    help: str | None = None


@dataclass(frozen=True)
class CategorySpec:
    id: str
    label: str
    title: str
    description: str
    filter_fields: tuple[FilterField, ...] = ()
    like_options: tuple[str, ...] = ()
    avoid_options: tuple[str, ...] = ()
    is_sample: bool = True
    custom: bool = False


@dataclass(frozen=True)
class Person:
    id: str
    name: str
    likes: tuple[str, ...] = ()
    avoids: tuple[str, ...] = ()


@dataclass(frozen=True)
class SearchRequest:
    category_id: str
    people: tuple[Person, ...]
    query: str = ""
    filters: dict[str, Any] = field(default_factory=dict)
    limit: int = 30
    custom_options: tuple[str, ...] = ()


@dataclass(frozen=True)
class Candidate:
    category_id: str
    id: str
    title: str
    description: str = ""
    facts: dict[str, str] = field(default_factory=dict)
    tags: tuple[str, ...] = ()
    matched_likes: dict[str, tuple[str, ...]] = field(default_factory=dict)
    reasons: tuple[str, ...] = ()
    source_url: str | None = None
    image_url: str | None = None


@dataclass(frozen=True)
class SearchResponse:
    candidates: tuple[Candidate, ...]
    total_found: int | None = None
    warnings: tuple[str, ...] = ()
    engine: str = "Typesense"
    search_time_ms: int | None = None


@dataclass(frozen=True)
class SeedReport:
    category_id: str
    imported: int
    failed: int = 0
    errors: tuple[str, ...] = ()


def validate_response(response: SearchResponse, request: SearchRequest) -> None:
    if not isinstance(response, SearchResponse):
        raise CategorySearchError("Category must return a SearchResponse. Check TEAM_HANDOFF.md.")
    ids: set[str] = set()
    people = {p.id: p for p in request.people}
    for candidate in response.candidates:
        if not isinstance(candidate, Candidate) or candidate.category_id != request.category_id:
            raise CategorySearchError("Category returned an invalid result type or category ID.")
        if not candidate.id or not candidate.title or candidate.id in ids:
            raise CategorySearchError("Every result needs a unique stable ID and a title.")
        ids.add(candidate.id)
        for person_id, matches in candidate.matched_likes.items():
            if person_id not in people or not set(matches) <= set(people[person_id].likes):
                raise CategorySearchError("A result claims a preference that was not selected.")
