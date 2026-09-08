"""Pure state helpers, kept separate from Streamlit for reliable testing."""
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4
from core.contracts import Candidate, CategorySpec, Person, SearchResponse


@dataclass
class CategoryState:
    filters: dict[str, Any] = field(default_factory=dict)
    query: str = ""
    preferences: dict[str, dict[str, tuple[str, ...]]] = field(default_factory=dict)
    custom_text: str = ""
    results: list[Candidate] = field(default_factory=list)
    response: SearchResponse | None = None
    shortlist: list[Candidate] = field(default_factory=list)
    votes: dict[str, dict[str, int]] = field(default_factory=dict)
    chosen_id: str | None = None
    searched: bool = False
    revision: int = 0

    def invalidate(self) -> None:
        self.results.clear()
        self.response = None
        self.shortlist.clear()
        self.votes.clear()
        self.chosen_id = None
        self.searched = False
        self.revision += 1

    def set_preferences(self, person_id: str, likes: list[str], avoids: list[str]) -> None:
        value = {"likes": tuple(likes), "avoids": tuple(avoids)}
        if self.preferences.get(person_id, {"likes": (), "avoids": ()}) != value:
            self.preferences[person_id] = value
            self.invalidate()
        else:
            self.preferences[person_id] = value

    def toggle_shortlist(self, candidate: Candidate) -> None:
        if any(c.id == candidate.id for c in self.shortlist):
            self.shortlist = [c for c in self.shortlist if c.id != candidate.id]
            self.votes.pop(candidate.id, None)
        elif len(self.shortlist) < 3:
            self.shortlist.append(candidate)
        else:
            raise ValueError("Choose up to three options for your shortlist.")
        self.chosen_id = None


@dataclass
class GroupState:
    members: list[dict[str, str]] = field(default_factory=lambda: [
        {"id": "person-1", "name": "You"}, {"id": "person-2", "name": "Friend"}])
    categories: dict[str, CategoryState] = field(default_factory=dict)

    def category(self, spec: CategorySpec) -> CategoryState:
        if spec.id not in self.categories:
            self.categories[spec.id] = CategoryState(
                filters={f.key: f.default for f in spec.filter_fields})
        return self.categories[spec.id]

    def people(self, state: CategoryState) -> tuple[Person, ...]:
        return tuple(Person(m["id"], m["name"],
                           state.preferences.get(m["id"], {}).get("likes", ()),
                           state.preferences.get(m["id"], {}).get("avoids", ())) for m in self.members)

    def invalidate_all(self) -> None:
        for state in self.categories.values():
            state.invalidate()

    def add(self, name: str) -> str:
        name = name.strip()
        if not name or len(name) > 40:
            raise ValueError("Enter a name between 1 and 40 characters.")
        if len(self.members) >= 12:
            raise ValueError("This local demo supports up to 12 people.")
        person_id = uuid4().hex
        self.members.append({"id": person_id, "name": name})
        self.invalidate_all()
        return person_id

    def remove(self, person_id: str) -> None:
        if len(self.members) <= 1:
            raise ValueError("Keep at least one person in your group.")
        self.members = [m for m in self.members if m["id"] != person_id]
        for state in self.categories.values():
            state.preferences.pop(person_id, None)
        self.invalidate_all()
