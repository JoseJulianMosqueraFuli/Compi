"""Builds, stores and recalculates the recommended week; records what was done against it."""
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

from sqlmodel import Session, col, select

from app.models.domain import SessionKind, SessionStatus, WorkoutType
from app.models.training import (
    TRAINING_PREFERENCES_SINGLETON_ID,
    AvailabilityException,
    AvailabilityWindow,
    PlanChange,
    RecommendedSession,
    TrainingPreferences,
    WeekPlan,
)
from app.models.workout import (
    CardioDetail,
    ExerciseSet,
    Workout,
    WorkoutExercise,
    recompute_strength_summary,
)
from app.services.recommender.availability import (
    ExceptionSpec,
    WindowSpec,
    resolve_slots,
    week_start_of,
)
from app.services.recommender.catalog import EXERCISES, TEMPLATES, split_for
from app.services.recommender.compare import DoneExercise, DoneSet, SessionComparison, compare
from app.services.recommender.duration import (
    estimated_minutes,
    learn_duration_factor,
    model_minutes,
)
from app.services.recommender.scheduler import (
    Placement,
    Schedule,
    SessionState,
    replan,
)
from app.services.recommender.shorten import minimal_version, shorten
from app.services.recommender.training import (
    CardioOutcome,
    History,
    Performance,
    PerformedSet,
    cardio_prescription,
    strength_prescription,
)
from app.services.recommender.types import (
    ExercisePrescription,
    Prescription,
    Slot,
    fmt_clock,
    fmt_day,
)

MAX_CARRIED_PER_SESSION = 2
CARDIO_TITLES = {SessionKind.RUN: "Carrera suave", SessionKind.WALK: "Caminata"}
TRIGGER_REASONS = {
    "availability": "Cambió tu disponibilidad.",
    "manual": "Pediste recalcular la semana.",
    "status": "Reabriste una sesión.",
}


class SessionAlreadyLoggedError(ValueError):
    """The recommended session already has a workout recorded against it."""


class WorkoutMismatchError(ValueError):
    """The workout cannot be recorded against this session."""


# --- preferences and clock -------------------------------------------------------------


def get_preferences(session: Session) -> TrainingPreferences:
    prefs = session.get(TrainingPreferences, TRAINING_PREFERENCES_SINGLETON_ID)
    if prefs is None:
        prefs = TrainingPreferences()
        session.add(prefs)
        session.flush()
    return prefs


def local_now(prefs: TrainingPreferences, now: datetime) -> datetime:
    """`now` (aware) as naive wall-clock time in the user's zone, where windows live."""
    return now.astimezone(ZoneInfo(prefs.timezone)).replace(tzinfo=None)


def _to_time(minutes: int) -> time:
    return time(hour=minutes // 60, minute=minutes % 60)


def _to_minutes(t: time) -> int:
    return t.hour * 60 + t.minute


# --- inputs for the pure recommender -----------------------------------------------------


def load_slots(session: Session, week_start: date, now_local: datetime | None) -> list[Slot]:
    week_end = week_start + timedelta(days=6)
    windows = [
        WindowSpec(w.weekday, w.start_time, w.end_time, w.gym_access)
        for w in session.exec(select(AvailabilityWindow)).all()
    ]
    exceptions = [
        ExceptionSpec(e.day, e.start_time, e.end_time, e.gym_access)
        for e in session.exec(
            select(AvailabilityException).where(
                col(AvailabilityException.day) >= week_start,
                col(AvailabilityException.day) <= week_end,
            )
        ).all()
    ]
    return resolve_slots(week_start, windows, exceptions, now_local)


def load_history(session: Session, prefs: TrainingPreferences) -> History:
    """Performed sets per catalog exercise, most recent first."""
    zone = ZoneInfo(prefs.timezone)
    rows = session.exec(
        select(WorkoutExercise, Workout)
        .join(Workout, col(WorkoutExercise.workout_id) == col(Workout.id))
        .where(col(WorkoutExercise.exercise_key).is_not(None))
        .order_by(col(Workout.start_time).desc())
    ).all()
    history: dict[str, list[Performance]] = {}
    for exercise, workout in rows:
        sets = tuple(PerformedSet(s.reps, s.weight_kg, s.rpe) for s in exercise.sets)
        if sets and exercise.exercise_key:
            day = workout.start_time.astimezone(zone).date()
            history.setdefault(exercise.exercise_key, []).append(Performance(day, sets))
    return history


def duration_samples(session: Session) -> list[tuple[float, float]]:
    """(model minutes, real minutes) of completed strength sessions, most recent first."""
    rows = session.exec(
        select(RecommendedSession, Workout)
        .join(Workout, col(RecommendedSession.workout_id) == col(Workout.id))
        .where(
            RecommendedSession.kind == SessionKind.STRENGTH,
            RecommendedSession.status == SessionStatus.DONE,
        )
        .order_by(col(Workout.start_time).desc())
    ).all()
    return [
        (model_minutes(Prescription.model_validate(rec.prescription)), workout.duration_s / 60)
        for rec, workout in rows
        if workout.duration_s > 0
    ]


def _previous_cardio(session: Session, week_start: date, kind: SessionKind) -> list[CardioOutcome]:
    previous = session.exec(
        select(WeekPlan)
        .where(col(WeekPlan.week_start) < week_start)
        .order_by(col(WeekPlan.week_start).desc())
    ).first()
    if previous is None:
        return []
    return [
        CardioOutcome(
            target_min=Prescription.model_validate(s.base_prescription).target_minutes or 0,
            status=s.status,
        )
        for s in sessions_of(session, previous)
        if s.kind is kind
    ]


def sessions_of(session: Session, plan: WeekPlan) -> list[RecommendedSession]:
    return list(
        session.exec(
            select(RecommendedSession)
            .where(RecommendedSession.week_plan_id == plan.id)
            .order_by(col(RecommendedSession.order_index))
        ).all()
    )


def changes_of(session: Session, plan: WeekPlan, limit: int = 30) -> list[PlanChange]:
    return list(
        session.exec(
            select(PlanChange)
            .where(PlanChange.week_plan_id == plan.id)
            .order_by(col(PlanChange.id).desc())
            .limit(limit)
        ).all()
    )


# --- building a week ---------------------------------------------------------------------


def _new_sessions(
    session: Session,
    plan: WeekPlan,
    prefs: TrainingPreferences,
    kept: Sequence[RecommendedSession],
    factor: float,
    today: date,
) -> list[RecommendedSession]:
    """Sessions still owed this week, each with its full (base) prescription."""
    history = load_history(session, prefs)
    kept_templates = {s.template_key for s in kept}
    kept_count = {k: sum(1 for s in kept if s.kind is k) for k in SessionKind}
    order = max((s.order_index for s in kept), default=0)
    created: list[RecommendedSession] = []

    def add(kind: SessionKind, template: str, title: str, base: Prescription) -> None:
        nonlocal order
        order += 1
        created.append(
            RecommendedSession(
                week_plan_id=plan.id,  # type: ignore[arg-type]
                order_index=order,
                kind=kind,
                template_key=template,
                title=title,
                requires_gym=kind is SessionKind.STRENGTH,
                full_minutes=estimated_minutes(base, factor),
                min_minutes=estimated_minutes(minimal_version(base), factor),
                base_prescription=base.model_dump(mode="json"),
                prescription=base.model_dump(mode="json"),
            )
        )

    templates = [
        t for t in split_for(prefs.strength_sessions_per_week) if t not in kept_templates
    ]
    owed = max(0, prefs.strength_sessions_per_week - kept_count[SessionKind.STRENGTH])
    for template in templates[:owed]:
        base, notes = strength_prescription(template, history, today, prefs.excluded_exercises)
        if not base.exercises:
            continue
        fitted = shorten(base, prefs.strength_minutes, factor)
        if fitted is None:
            base = minimal_version(base)
            notes.append(
                f"Tu duración objetivo de {prefs.strength_minutes} min no alcanza ni para la "
                "versión mínima: se deja solo lo principal."
            )
        elif fitted.notes:
            base = fitted.prescription
            notes.append(
                f"Ajustada a tu duración objetivo de {prefs.strength_minutes} min: "
                + " ".join(fitted.notes)
            )
        if factor != 1.0:
            notes.append(
                f"Tus sesiones de fuerza duran ×{factor:g} respecto a la estimación inicial; "
                "el tiempo reservado ya lo tiene en cuenta."
            )
        add(
            SessionKind.STRENGTH,
            template,
            TEMPLATES[template].title,
            base.model_copy(update={"notes": notes}),
        )

    for kind, wanted, minutes in (
        (SessionKind.RUN, prefs.run_sessions_per_week, prefs.run_minutes),
        (SessionKind.WALK, prefs.walk_sessions_per_week, prefs.walk_minutes),
    ):
        base = cardio_prescription(kind, minutes, _previous_cardio(session, plan.week_start, kind))
        for _ in range(max(0, wanted - kept_count[kind])):
            add(kind, kind.value, CARDIO_TITLES[kind], base)
    return created


def generate_week(
    session: Session, day: date, now: datetime, regenerate: bool = False
) -> WeekPlan:
    """Create the recommended week containing `day`, or rebuild what is still pending.

    Regenerating never touches sessions that were done, partially done or skipped.
    """
    prefs = get_preferences(session)
    now_local = local_now(prefs, now)
    week_start = week_start_of(day)
    plan = session.exec(select(WeekPlan).where(WeekPlan.week_start == week_start)).first()
    if plan is not None and not regenerate:
        return plan

    factor = learn_duration_factor(duration_samples(session))
    if plan is None:
        plan = WeekPlan(week_start=week_start, duration_factor=factor)
        session.add(plan)
        session.flush()
    kept: list[RecommendedSession] = []
    for existing in sessions_of(session, plan):
        if existing.status is SessionStatus.PENDING:
            for change in session.exec(
                select(PlanChange).where(PlanChange.session_id == existing.id)
            ).all():
                change.session_id = None
            session.delete(existing)
        else:
            kept.append(existing)
    session.flush()

    plan.duration_factor = factor
    plan.updated_at = datetime.now(UTC)
    created = _new_sessions(session, plan, prefs, kept, factor, now_local.date())
    session.add_all(created)
    session.flush()

    _replan(session, plan, now_local, factor, trigger=None)
    return plan


# --- recalculating -----------------------------------------------------------------------


@dataclass(frozen=True)
class _Snapshot:
    day: date | None
    start_time: time | None
    minutes: int | None
    exercises: tuple[tuple[str, int], ...]
    target_minutes: int | None

    @classmethod
    def of(cls, s: RecommendedSession) -> "_Snapshot":
        p = Prescription.model_validate(s.prescription)
        return cls(
            s.day,
            s.start_time,
            s.planned_minutes,
            tuple((e.key, len(e.sets)) for e in p.exercises),
            p.target_minutes,
        )


def _state(s: RecommendedSession) -> SessionState:
    return SessionState(
        id=s.id,
        kind=s.kind,
        requires_gym=s.requires_gym,
        full_min=s.full_minutes,
        min_min=s.min_minutes,
        # A skipped session did not happen: it neither holds a window nor counts for spacing.
        pending=s.status is SessionStatus.PENDING,
        day=None if s.status is SessionStatus.SKIPPED else s.day,
        start_min=_to_minutes(s.start_time) if s.start_time else None,
    )


def _placement_reasons(
    s: RecommendedSession, placement: Placement, placements: dict, by_id: dict
) -> list[str]:
    slot = placement.slot
    where = (
        f"{fmt_day(slot.day).capitalize()}, ventana de {fmt_clock(slot.start_min)} a "
        f"{fmt_clock(slot.end_min)} ({slot.minutes} min"
        + (", con gimnasio)." if slot.gym_access else ").")
    )
    reasons = [where]
    others = {
        other.id: (p.day if (p := placements.get(other.id)) else other.day)
        for other in by_id.values()
        if other.id != s.id and other.status is not SessionStatus.SKIPPED
    }
    same_kind = [d for i, d in others.items() if d and by_id[i].kind is s.kind]
    if s.kind is SessionKind.STRENGTH and same_kind:
        if any(abs((d - slot.day).days) < 2 for d in same_kind):
            reasons.append(
                "Queda pegada a otra sesión de fuerza: con tus ventanas no había forma de "
                "dejar un día entre ambas."
            )
        else:
            reasons.append("Deja al menos un día de recuperación entre sesiones de fuerza.")
    sharing = [by_id[i].title for i, d in others.items() if d == slot.day]
    if sharing:
        reasons.append(
            f"Comparte día con {', '.join(sharing)}: no quedaba un día libre que sirviera."
        )
    return reasons


def _carry_over(
    sources: list[tuple[RecommendedSession, list[ExercisePrescription]]],
    targets: dict[int, tuple[RecommendedSession, Placement, Prescription, list[str]]],
    factor: float,
    cuts: dict[int, list[str]],
) -> None:
    """Move exercises that were cut from a shortened session into another pending strength
    session of the week that still has spare time in its window."""
    for source, dropped in sources:
        if source.day is None:
            continue
        candidates = sorted(
            (t for i, t in targets.items() if i != source.id),
            key=lambda t: (abs((t[1].day - source.day).days), t[1].day),  # type: ignore[operator]
        )
        for exercise in dropped:
            for target, placement, prescription, reasons in candidates:
                carried = sum(1 for e in prescription.exercises if e.carried_from)
                if carried >= MAX_CARRIED_PER_SESSION:
                    continue
                if any(e.key == exercise.key for e in prescription.exercises):
                    continue
                moved = exercise.model_copy(
                    update={
                        "priority": 3,
                        "carried_from": f"{source.title}, {fmt_day(source.day)}",
                    }
                )
                extended = prescription.model_copy(
                    update={"exercises": [*prescription.exercises, moved]}
                )
                if estimated_minutes(extended, factor) > placement.slot.minutes:
                    continue
                prescription.exercises.append(moved)
                reasons.append(
                    f"Se añade {exercise.name}, que no cabía el {fmt_day(source.day)}."
                )
                note = f"{exercise.name} pasa a {target.title} ({fmt_day(placement.day)})."
                source.reasons = [*source.reasons, note]
                cuts.setdefault(source.id, []).append(note)  # type: ignore[arg-type]
                cuts.setdefault(target.id, []).append(  # type: ignore[arg-type]
                    f"Se añade {exercise.name}, que no cabía el {fmt_day(source.day)}."
                )
                break


def _describe_change(
    s: RecommendedSession,
    before: _Snapshot,
    after: _Snapshot,
    today: date,
    why: str,
    cut_notes: Sequence[str],
) -> tuple[str, str, str] | None:
    """(kind, summary, reason) of what changed for a session, or None if nothing did."""
    if before == after:
        return None
    when = (
        f"{fmt_day(after.day)} a las {after.start_time:%H:%M}"
        if after.day and after.start_time
        else ""
    )
    detail = " ".join(cut_notes)
    if after.day is None:
        return ("unscheduled", f"{s.title} ya no cabe esta semana.", s.reasons[0])
    if before.day is None:
        return ("scheduled", f"{s.title} ahora cabe el {when} ({after.minutes} min).", why)
    if before.day != after.day:
        reason = (
            f"El {fmt_day(before.day)} pasó sin que la registraras."
            if before.day < today
            else f"Su ventana del {fmt_day(before.day)} ya no puede alojarla."
        )
        summary = f"{s.title} pasa del {fmt_day(before.day)} al {when} ({after.minutes} min)."
        if (after.minutes or 0) < (before.minutes or 0):
            summary += f" Versión más corta. {detail}"
        return ("moved", summary.strip(), reason)
    if (after.minutes or 0) < (before.minutes or 0):
        return (
            "shortened",
            f"{s.title} del {fmt_day(after.day)} se acorta de {before.minutes} a "
            f"{after.minutes} min. {detail}".strip(),
            f"{why} {s.reasons[0]}",
        )
    if (after.minutes or 0) > (before.minutes or 0):
        return (
            "extended",
            f"{s.title} del {fmt_day(after.day)} pasa de {before.minutes} a "
            f"{after.minutes} min. {detail}".strip(),
            f"{why} {s.reasons[0]}",
        )
    if before.start_time != after.start_time:
        return (
            "retimed",
            f"{s.title} del {fmt_day(after.day)} empieza a las {after.start_time:%H:%M} "
            f"(antes {before.start_time:%H:%M}).",
            why,
        )
    return ("adjusted", f"{s.title} del {fmt_day(after.day)} cambia de contenido. {detail}", why)


def _replan(
    session: Session,
    plan: WeekPlan,
    now_local: datetime,
    factor: float,
    trigger: str | None,
) -> list[PlanChange]:
    """Place every pending session of the plan and store the outcome.

    With a trigger, each difference from the previous placement is logged as a PlanChange.
    """
    all_sessions = sessions_of(session, plan)
    by_id = {s.id: s for s in all_sessions}
    pending = [s for s in all_sessions if s.status is SessionStatus.PENDING]
    before = {s.id: _Snapshot.of(s) for s in pending}

    for s in pending:
        base = Prescription.model_validate(s.base_prescription)
        s.full_minutes = estimated_minutes(base, factor)
        s.min_minutes = estimated_minutes(minimal_version(base), factor)

    slots = load_slots(session, plan.week_start, now_local)
    schedule: Schedule = replan([_state(s) for s in all_sessions], slots)

    staged: dict[int, tuple[RecommendedSession, Placement, Prescription, list[str]]] = {}
    cut: list[tuple[RecommendedSession, list[ExercisePrescription]]] = []
    cuts: dict[int, list[str]] = {}
    for s in pending:
        base = Prescription.model_validate(s.base_prescription)
        placement = schedule.placements.get(s.id)
        fitted = shorten(base, placement.slot.minutes, factor) if placement else None
        if placement is None or fitted is None:
            s.day, s.start_time, s.planned_minutes = None, None, None
            s.prescription = base.model_dump(mode="json")
            s.reasons = [
                "Sin ventana esta semana. "
                + schedule.unscheduled.get(s.id, "No cabe en ninguna ventana libre.")
            ]
            continue
        s.day = placement.day
        s.start_time = _to_time(placement.start_min)
        reasons = _placement_reasons(s, placement, schedule.placements, by_id)
        if base.reason:
            reasons.append(base.reason)
        reasons.extend(base.notes)
        if fitted.notes:
            cuts[s.id] = list(fitted.notes)  # type: ignore[index]
            reasons.append(
                f"La versión completa pide {s.full_minutes} min y la ventana tiene "
                f"{placement.slot.minutes}: " + " ".join(fitted.notes)
            )
        s.reasons = reasons
        prescription = fitted.prescription.model_copy(deep=True)
        if s.kind is SessionKind.STRENGTH:
            staged[s.id] = (s, placement, prescription, [])  # type: ignore[index]
            if fitted.dropped:
                cut.append((s, fitted.dropped))
        else:
            s.prescription = prescription.model_dump(mode="json")
            s.planned_minutes = estimated_minutes(prescription, factor)

    _carry_over(cut, staged, factor, cuts)
    for s, _placement, prescription, extra in staged.values():
        s.prescription = prescription.model_dump(mode="json")
        s.planned_minutes = estimated_minutes(prescription, factor)
        s.reasons = [*s.reasons, *extra]

    changes: list[PlanChange] = []
    now_utc = datetime.now(UTC)
    for s in pending:
        s.updated_at = now_utc
        session.add(s)
        if trigger is None:
            continue
        described = _describe_change(
            s,
            before[s.id],
            _Snapshot.of(s),
            now_local.date(),
            TRIGGER_REASONS[trigger],
            cuts.get(s.id, ()),  # type: ignore[arg-type]
        )
        if described is None:
            continue
        kind, summary, reason = described
        change = PlanChange(
            week_plan_id=plan.id,  # type: ignore[arg-type]
            session_id=s.id,
            trigger=trigger,
            kind=kind,
            summary=summary,
            reason=reason,
        )
        session.add(change)
        changes.append(change)
    plan.duration_factor = factor
    plan.updated_at = now_utc
    session.add(plan)
    session.flush()
    return changes


def replan_week(session: Session, plan: WeekPlan, now: datetime, trigger: str) -> list[PlanChange]:
    """Recalculate the pending sessions of one week."""
    prefs = get_preferences(session)
    factor = learn_duration_factor(duration_samples(session))
    return _replan(session, plan, local_now(prefs, now), factor, trigger)


def replan_active_weeks(session: Session, now: datetime, trigger: str) -> list[PlanChange]:
    """Recalculate every stored week that has not ended yet."""
    prefs = get_preferences(session)
    today = local_now(prefs, now).date()
    plans = session.exec(
        select(WeekPlan)
        .where(col(WeekPlan.week_start) >= week_start_of(today))
        .order_by(col(WeekPlan.week_start))
    ).all()
    changes: list[PlanChange] = []
    for plan in plans:
        changes.extend(replan_week(session, plan, now, trigger))
    return changes


# --- recording what was done -------------------------------------------------------------


@dataclass(frozen=True)
class LoggedSet:
    reps: int
    weight_kg: float
    rest_s: int | None = None
    rpe: float | None = None


@dataclass(frozen=True)
class LoggedExercise:
    exercise_key: str | None
    name: str | None
    sets: Sequence[LoggedSet]


def replace_exercises(
    session: Session, workout: Workout, exercises: Sequence[LoggedExercise]
) -> None:
    """Store the sets of a strength workout one by one, replacing any previous log."""
    if workout.type is not WorkoutType.STRENGTH:
        raise WorkoutMismatchError("only strength workouts hold exercises")
    for old in list(workout.exercises):
        session.delete(old)
    session.flush()
    session.refresh(workout)
    rows: list[WorkoutExercise] = []
    for i, exercise in enumerate(exercises, start=1):
        known = EXERCISES.get(exercise.exercise_key or "")
        row = WorkoutExercise(
            workout_id=workout.id,  # type: ignore[arg-type]
            order_index=i,
            exercise_key=known.key if known else None,
            name=exercise.name or (known.name if known else "Ejercicio"),
        )
        row.sets = [
            ExerciseSet(order_index=j, reps=s.reps, weight_kg=s.weight_kg, rest_s=s.rest_s, rpe=s.rpe)
            for j, s in enumerate(exercise.sets, start=1)
        ]
        rows.append(row)
    workout.exercises = rows
    recompute_strength_summary(workout, rows)
    session.add(workout)
    session.flush()
    refresh_linked_status(session, workout)


def _performed(workout: Workout) -> list[DoneExercise]:
    return [
        DoneExercise(
            key=e.exercise_key,
            name=e.name,
            sets=tuple(DoneSet(s.reps, s.weight_kg) for s in e.sets),
        )
        for e in workout.exercises
    ]


def comparison_for(session: Session, rec: RecommendedSession) -> SessionComparison | None:
    """Recommended versus performed for a session that has a workout recorded."""
    if rec.workout_id is None:
        return None
    workout = session.get(Workout, rec.workout_id)
    if workout is None:
        return None
    return compare(
        Prescription.model_validate(rec.prescription), _performed(workout), workout.duration_s / 60
    )


def refresh_linked_status(session: Session, workout: Workout) -> None:
    """Re-derive done/partial for the session a workout is recorded against, if any."""
    for rec in session.exec(
        select(RecommendedSession).where(RecommendedSession.workout_id == workout.id)
    ).all():
        result = comparison_for(session, rec)
        if result is not None:
            rec.status = result.status
            rec.updated_at = datetime.now(UTC)
            session.add(rec)


def log_session(
    session: Session,
    rec: RecommendedSession,
    now: datetime,
    *,
    workout: Workout | None = None,
    started_at: datetime | None = None,
    duration_min: float | None = None,
    exercises: Sequence[LoggedExercise] = (),
    distance_km: float | None = None,
    perceived_effort: int | None = None,
    notes: str | None = None,
) -> RecommendedSession:
    """Record what was actually done for a recommended session.

    The recommendation is left exactly as it was: the log goes to a Workout (a new manual
    one, or an existing synced one passed as `workout`) that the session then points to.
    """
    if rec.workout_id is not None:
        raise SessionAlreadyLoggedError(rec.id)
    prefs = get_preferences(session)
    zone = ZoneInfo(prefs.timezone)
    wanted_type = rec.kind.workout_type

    if workout is not None:
        if workout.type is not wanted_type:
            raise WorkoutMismatchError("the workout is not of the kind this session asks for")
        taken = session.exec(
            select(RecommendedSession).where(RecommendedSession.workout_id == workout.id)
        ).first()
        if taken is not None:
            raise WorkoutMismatchError("the workout is already recorded against another session")
        if duration_min is not None:
            workout.duration_s = int(round(duration_min * 60))
    else:
        if duration_min is None:
            raise WorkoutMismatchError("duration_min is required when no workout is given")
        duration_s = int(round(duration_min * 60))
        if started_at is None:
            started_at = now - timedelta(seconds=duration_s)
        elif started_at.tzinfo is None:
            started_at = started_at.replace(tzinfo=zone)
        workout = Workout(
            external_id=f"manual-{uuid4().hex}",
            type=wanted_type,
            start_time=started_at.astimezone(UTC),
            duration_s=duration_s,
        )
    if rec.kind is not SessionKind.STRENGTH:
        workout.subtype = rec.kind.value
    if perceived_effort is not None:
        workout.perceived_effort = perceived_effort
    if notes is not None:
        workout.notes = notes
    session.add(workout)
    session.flush()

    rec.workout_id = workout.id
    session.add(rec)
    if rec.kind is SessionKind.STRENGTH:
        if exercises:
            replace_exercises(session, workout, exercises)
        elif workout.exercises:
            # Linking a workout whose sets were already logged: keep them.
            refresh_linked_status(session, workout)
        else:
            raise WorkoutMismatchError("a strength session needs at least one exercise logged")
    else:
        if distance_km is not None:
            detail = workout.cardio_detail or CardioDetail(workout_id=workout.id)  # type: ignore[arg-type]
            detail.distance_m = distance_km * 1000
            if distance_km > 0:
                detail.avg_pace_s_per_km = workout.duration_s / distance_km
            session.add(detail)
            session.flush()
        refresh_linked_status(session, workout)
    session.flush()
    return rec


# --- judging the recommender -------------------------------------------------------------


def evaluation(session: Session) -> dict:
    """Estimated versus real duration, adherence and voluntary changes over logged sessions,
    plus the progression of each exercise and of the runs."""
    prefs = get_preferences(session)
    zone = ZoneInfo(prefs.timezone)
    recs = session.exec(select(RecommendedSession)).all()
    by_status = {status.value: 0 for status in SessionStatus}
    durations: list[dict] = []
    adherences: list[float] = []
    adjustments = {"weight_changed": 0, "added": 0, "omitted": 0, "partial": 0}
    for rec in recs:
        by_status[rec.status.value] += 1
        result = comparison_for(session, rec)
        if result is None:
            continue
        adherences.append(result.adherence)
        for row in result.exercises:
            adjustments["weight_changed"] += row.weight_changed
            if row.outcome in adjustments:
                adjustments[row.outcome] += 1
        if rec.planned_minutes and result.actual_minutes:
            durations.append(
                {
                    "session_id": rec.id,
                    "title": rec.title,
                    "day": rec.day,
                    "kind": rec.kind,
                    "estimated_min": rec.planned_minutes,
                    "actual_min": result.actual_minutes,
                }
            )
    errors = [abs(d["actual_min"] - d["estimated_min"]) for d in durations]

    strength: dict[str, list[dict]] = {}
    for key, performances in load_history(session, prefs).items():
        strength[key] = [
            {
                "day": p.day,
                "top_weight_kg": max(s.weight_kg for s in p.sets),
                "best_reps": max(s.reps for s in p.sets),
                "volume_kg": sum(s.reps * s.weight_kg for s in p.sets),
            }
            for p in reversed(performances)
        ]
    runs = [
        {
            "day": w.start_time.astimezone(zone).date(),
            "minutes": round(w.duration_s / 60, 1),
            "distance_km": round(w.cardio_detail.distance_m / 1000, 2)
            if w.cardio_detail and w.cardio_detail.distance_m
            else None,
            "pace_s_per_km": w.cardio_detail.avg_pace_s_per_km if w.cardio_detail else None,
        }
        for w in session.exec(
            select(Workout).where(Workout.subtype == "run").order_by(col(Workout.start_time))
        ).all()
    ]
    return {
        "sessions": by_status,
        "duration_factor": learn_duration_factor(duration_samples(session)),
        "duration_mean_abs_error_min": round(sum(errors) / len(errors), 1) if errors else None,
        "durations": sorted(durations, key=lambda d: (d["day"] is None, d["day"])),
        "mean_adherence": round(sum(adherences) / len(adherences), 3) if adherences else None,
        "adjustments": adjustments,
        "strength_progress": [
            {"key": k, "name": EXERCISES[k].name if k in EXERCISES else k, "points": v}
            for k, v in sorted(strength.items())
        ],
        "runs": runs,
    }
