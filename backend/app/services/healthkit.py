"""Apply one ordered HealthKit page and its checkpoint in the same transaction."""

from datetime import datetime
from hashlib import sha256

from sqlalchemy import delete, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlmodel import Session

from app.models.health import HealthObservation, HealthSyncCursor
from app.models.health_schemas import HealthBatchIn


class HealthStreamConflictError(ValueError):
    """A stream was replaced, a page was skipped or a retry has different contents."""


def apply_batch(session: Session, batch: HealthBatchIn, now: datetime) -> bool:
    """Return False for a retry of the last acknowledged page.

    The conditional UPDATE locks the cursor until the sample changes commit.
    Independent API workers can process the same retry safely. A single iPhone
    owns each kind in this version; a fresh stream cannot overwrite its history.
    """
    insert = pg_insert if session.get_bind().dialect.name == "postgresql" else sqlite_insert
    cursors = HealthSyncCursor.__table__
    observations = HealthObservation.__table__
    digest = sha256(batch.model_dump_json().encode()).hexdigest()
    with session.begin():
        if batch.sequence == 1:
            session.execute(
                insert(cursors)
                .values(
                    kind=batch.kind,
                    stream_id=batch.stream_id,
                    last_sequence=0,
                    last_digest="",
                    updated_at=now,
                )
                .on_conflict_do_nothing()
            )
        advanced = session.execute(
            update(cursors)
            .where(
                cursors.c.kind == batch.kind,
                cursors.c.stream_id == batch.stream_id,
                cursors.c.last_sequence == batch.sequence - 1,
            )
            .values(last_sequence=batch.sequence, last_digest=digest, updated_at=now)
        )
        if advanced.rowcount == 0:
            cursor = session.get(HealthSyncCursor, batch.kind)
            if (
                cursor
                and cursor.stream_id == batch.stream_id
                and cursor.last_sequence == batch.sequence
                and cursor.last_digest == digest
            ):
                return False
            raise HealthStreamConflictError("stream or sequence conflicts with the committed checkpoint")

        if batch.deletions:
            session.execute(
                delete(observations).where(
                    observations.c.kind == batch.kind,
                    observations.c.sample_id.in_(batch.deletions),
                )
            )
        if batch.upserts:
            rows = [
                {
                    "kind": batch.kind,
                    "sample_id": sample.sample_id,
                    "source_bundle": sample.source_bundle,
                    "start": sample.start,
                    "end": sample.end,
                    "numeric_value": sample.value if isinstance(sample.value, float) else None,
                    "category_value": sample.value if isinstance(sample.value, str) else None,
                    "duration_s": sample.duration_s,
                }
                for sample in batch.upserts
            ]
            statement = insert(observations)
            mutable = ["source_bundle", "start", "end", "numeric_value", "category_value", "duration_s"]
            session.execute(
                statement.on_conflict_do_update(
                    index_elements=["kind", "sample_id"],
                    set_={name: statement.excluded[name] for name in mutable},
                ),
                rows,
            )
    return True
