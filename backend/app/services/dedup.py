"""Pure deduplication helper (Req 6.2, 6.3, Property 1)."""
from collections.abc import Iterable

from app.providers.base import ExternalWorkout


def partition_new_workouts(
    existing_ids: Iterable[str],
    fetched: Iterable[ExternalWorkout],
) -> tuple[list[ExternalWorkout], list[ExternalWorkout]]:
    """Split a batch of fetched workouts into (new, skipped) by external_id.

    - `new`: first occurrences of previously unseen external ids.
    - `skipped`: ids already stored or repeated within the same response.

    Insertion order from `fetched` is preserved within each output list.
    """
    existing = set(existing_ids)
    new: list[ExternalWorkout] = []
    skipped: list[ExternalWorkout] = []
    for w in fetched:
        if w.external_id in existing:
            skipped.append(w)
        else:
            existing.add(w.external_id)
            new.append(w)
    return new, skipped
