"""Clear one imported category locally before retiring or re-pairing a HealthKit stream."""

import argparse

from sqlalchemy import delete
from sqlmodel import Session

from app.db import engine
from app.models.health import HealthObservation, HealthSyncCursor


def clear_category(session: Session, kind: str) -> None:
    with session.begin():
        cursor = session.get(HealthSyncCursor, kind, with_for_update=True)
        if cursor is not None:
            session.execute(delete(HealthObservation).where(HealthObservation.kind == kind))
            session.delete(cursor)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kind", choices=("workout", "heart_rate", "sleep", "body_mass"), required=True)
    parser.add_argument("--confirm", action="store_true", help="Delete the imported samples and cursor.")
    args = parser.parse_args()
    if not args.confirm:
        parser.error("Stop the mobile receiver first, then pass --confirm to erase this category.")
    with Session(engine) as session:
        clear_category(session, args.kind)


if __name__ == "__main__":
    main()
