"""Property-based tests for periodization, progression and comparison (Properties 2, 7, 8)."""
from datetime import date, timedelta
from types import SimpleNamespace

from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st

from app.models.domain import PlannedVsActual
from app.services.compare_service import compare_planned_vs_actual
from app.services.plan_service import PlanService, PlanValidationError
from app.services.progression_service import DELOAD_FACTOR, compute_progression

# Feature: compi-training-platform, Property 2: Integridad de la jerarquía de periodización


@st.composite
def periodization_tree(draw: st.DrawFn) -> SimpleNamespace:
    """Generate a tree macrociclo -> meso -> micro -> sesion with valid dates."""
    macro_start = draw(
        st.dates(min_value=date(2020, 1, 1), max_value=date(2029, 12, 1))
    )
    macro_end = macro_start + timedelta(days=draw(st.integers(min_value=7, max_value=365)))
    meso_count = draw(st.integers(min_value=1, max_value=4))
    micro_count = draw(st.integers(min_value=1, max_value=5))
    meso_start = macro_start
    return SimpleNamespace(
        macro_start=macro_start,
        macro_end=macro_end,
        meso_count=meso_count,
        micro_count=micro_count,
        meso_start=meso_start,
    )


@settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(tree=periodization_tree())
def test_create_hierarchy_succeeds_when_invariants_hold(tree: SimpleNamespace) -> None:
    """Property 2: a tree with consistent dates builds and remains reachable."""

    class FakeRepo:
        def __init__(self) -> None:
            self.macrociclos: dict[int, SimpleNamespace] = {}
            self.mesociclos: dict[int, SimpleNamespace] = {}
            self.microciclos: dict[int, SimpleNamespace] = {}
            self.sesiones: dict[int, SimpleNamespace] = {}
            self._next = [1]

        def _id(self) -> int:
            i = self._next[0]
            self._next[0] += 1
            return i

        def create_macrociclo(self, m):
            m.id = self._id()
            self.macrociclos[m.id] = m
            return m

        def get_macrociclo(self, mid):
            return self.macrociclos[mid]

        def create_mesociclo(self, m):
            m.id = self._id()
            self.mesociclos[m.id] = m
            return m

        def get_mesociclo(self, mid):
            return self.mesociclos[mid]

        def get_microciclos(self, meso_id):
            return [m for m in self.microciclos.values() if m.mesociclo_id == meso_id]

        def get_microciclo(self, micro_id):
            return self.microciclos[micro_id]

        def create_microciclo(self, m):
            m.id = self._id()
            self.microciclos[m.id] = m
            return m

        def create_sesion(self, s):
            s.id = self._id()
            self.sesiones[s.id] = s
            return s

    repo = FakeRepo()
    service = PlanService(repo)  # type: ignore[arg-type]

    macro = service.create_macrociclo(
        name="Q", start_date=tree.macro_start, end_date=tree.macro_end
    )

    # Distribute the macrociclo into mesociclos with non-empty ranges, then
    # distribute each mesociclo into non-overlapping microciclos.
    total_days = (tree.macro_end - tree.macro_start).days
    assume(total_days >= tree.meso_count * tree.micro_count)
    meso_step = max(1, total_days // max(1, tree.meso_count))
    micro_step = max(1, meso_step // max(1, tree.micro_count))

    meso_start = tree.macro_start
    for mi in range(tree.meso_count):
        meso_end = meso_start + timedelta(days=meso_step)
        if meso_end > tree.macro_end:
            meso_end = tree.macro_end
        meso = service.create_mesociclo(
            macrociclo_id=macro.id,  # type: ignore[arg-type]
            name=f"M{mi}",
            order_index=mi + 1,
            start_date=meso_start,
            end_date=meso_end,
        )
        for ji in range(tree.micro_count):
            m_start = meso_start + timedelta(days=ji * micro_step)
            m_end = m_start + timedelta(days=micro_step)
            if m_end > meso_end:
                m_end = meso_end
            service.create_microciclo(
                mesociclo_id=meso.id,  # type: ignore[arg-type]
                order_index=ji + 1,
                start_date=m_start,
                end_date=m_end,
                base_load=100.0,
            )
        meso_start = meso_end

    assert len(repo.macrociclos) == 1
    assert len(repo.mesociclos) == tree.meso_count
    assert len(repo.microciclos) == tree.meso_count * tree.micro_count


@settings(max_examples=50)
@given(
    macro_start=st.dates(min_value=date(2020, 1, 1), max_value=date(2025, 1, 1)),
    duration=st.integers(min_value=30, max_value=365),
)
def test_mesociclo_outside_macrociclo_is_rejected(
    macro_start: date, duration: int
) -> None:
    """Property 2: a mesociclo outside the macrociclo range is rejected."""
    macro_end = macro_start + timedelta(days=duration)

    class FakeRepo:
        def get_macrociclo(self, mid):  # noqa: D401
            return SimpleNamespace(start_date=macro_start, end_date=macro_end)

    service = PlanService(FakeRepo())  # type: ignore[arg-type]
    with_outer = macro_start - timedelta(days=10)
    with_inner = with_outer + timedelta(days=5)
    assume(with_outer < macro_start)
    with __import__("pytest").raises(PlanValidationError):
        service.create_mesociclo(
            macrociclo_id=1,
            name="Bad",
            order_index=1,
            start_date=with_outer,
            end_date=with_inner,
        )


# Feature: compi-training-platform, Property 7: Secuencia de progresión con incremento y deload


@st.composite
def micro_sequence(draw: st.DrawFn) -> list[SimpleNamespace]:
    """A list of microciclos with order_index, is_deload, base_load and mesociclo increment."""
    n = draw(st.integers(min_value=1, max_value=8))
    items: list[SimpleNamespace] = []
    base = draw(st.floats(min_value=1.0, max_value=1000.0, allow_nan=False))
    inc_pct = draw(st.floats(min_value=-0.5, max_value=0.5, allow_nan=False))
    has_deload = draw(st.booleans())
    for i in range(n):
        items.append(
            SimpleNamespace(
                id=i + 1,
                order_index=i + 1,
                is_deload=has_deload and i > 0 and i == n - 1,
                base_load=base if i == 0 else None,
                mesociclo=SimpleNamespace(weekly_increment_pct=inc_pct),
            )
        )
    return items


@settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(items=micro_sequence())
def test_progression_property_7(items: list[SimpleNamespace]) -> None:
    """Property 7: increment is applied between non-deload microciclos, deload halves."""
    points = compute_progression(items)  # type: ignore[arg-type]
    assert len(points) == len(items)
    # First point comes from base_load.
    assert points[0].target_load == float(items[0].base_load)
    for prev, cur, m in zip(points, points[1:], items[1:], strict=False):
        if cur.is_deload:
            assert cur.target_load == prev.target_load * DELOAD_FACTOR
            assert cur.target_load < prev.target_load
        else:
            inc = m.mesociclo.weekly_increment_pct or 0.0
            assert cur.target_load == prev.target_load * (1.0 + inc)


@settings(max_examples=50)
@given(items=micro_sequence())
def test_progression_non_negative(items: list[SimpleNamespace]) -> None:
    """Property 7 (defensive): all target_loads are non-negative."""
    points = compute_progression(items)  # type: ignore[arg-type]
    for p in points:
        assert p.target_load >= 0


# Feature: compi-training-platform, Property 8: Comparación planificado vs. real


@settings(max_examples=100)
@given(
    planned=st.floats(min_value=0.0, max_value=10_000.0, allow_nan=False),
    actual=st.floats(min_value=0.0, max_value=10_000.0, allow_nan=False),
)
def test_compare_planned_vs_actual(planned: float, actual: float) -> None:
    """Property 8: delta = actual - planned; sign and zero are correct."""
    result = compare_planned_vs_actual(planned, actual)
    assert isinstance(result, PlannedVsActual)
    assert result.delta == actual - planned
    if actual > planned:
        assert result.delta > 0
    elif actual < planned:
        assert result.delta < 0
    else:
        assert result.delta == 0
        assert result.delta_pct == 0.0


@settings(max_examples=50)
@given(
    planned=st.floats(min_value=0.01, max_value=10_000.0, allow_nan=False),
    actual=st.floats(min_value=0.0, max_value=10_000.0, allow_nan=False),
)
def test_compare_delta_pct(planned: float, actual: float) -> None:
    """When planned > 0, delta_pct == delta / planned * 100."""
    result = compare_planned_vs_actual(planned, actual)
    expected = (actual - planned) / planned * 100.0
    assert abs(result.delta_pct - expected) < 1e-6
