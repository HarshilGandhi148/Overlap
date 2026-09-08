"""One explainable ranking policy shared by every category."""
from core.contracts import Candidate, Person


def preference_scores(candidate: Candidate, people: tuple[Person, ...]) -> list[float]:
    return [len(set(candidate.matched_likes.get(p.id, ())) & set(p.likes)) / len(set(p.likes))
            for p in people if p.likes]


def rank_candidates(candidates: tuple[Candidate, ...], people: tuple[Person, ...]) -> list[Candidate]:
    def key(candidate: Candidate) -> tuple[float, float]:
        scores = preference_scores(candidate, people)
        return (min(scores), sum(scores) / len(scores)) if scores else (0, 0)
    # Python's stable sort preserves provider relevance order for ties.
    return sorted(candidates, key=key, reverse=True)


def vote_status(votes: dict[str, int], people_ids: list[str]) -> tuple[bool, bool, int]:
    complete = bool(people_ids) and all(p in votes for p in people_ids)
    consensus = complete and all(votes[p] > 0 for p in people_ids)
    return complete, consensus, sum(votes.get(p, 0) for p in people_ids)
