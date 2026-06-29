"""Pure deduplication helper (Req 6.2, 6.3, Property 1)."""
from collections.abc import Iterable

from app.providers.base import ExternalWorkout


def partition_new_workouts(
    existing_ids: Iterable[str],
    fetched: Iterable[ExternalWorkout],
) -> tuple[list[ExternalWorkout], list[ExternalWorkout]]:
    """Split a batch of fetched workouts into (new, skipped) by external_id.

    - `new`: workouts whose external_id is NOT in `existing_ids`.
    - `skipped`: workouts whose external_id IS in `existing_ids` (Req 6.2 dedup).

    Insertion order from `fetched` is preserved within each output list.
    """
    existing = set(existing_ids)
    new: list[ExternalWorkout] = []
    skipped: list[ExternalWorkout] = []
    for w in fetched:
        if w.external_id in existing:
            skipped.append(w)
        else:
            new.append(w)
    return new, skipped
