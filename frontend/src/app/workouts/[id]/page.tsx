"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { api } from "@/lib/api";
import type { CatalogExercise, HRZonesResponse, SetIn, Workout } from "@/lib/types";

export default function WorkoutDetailPage() {
  const params = useParams<{ id: string }>();
  const id = Number(params.id);
  const [workout, setWorkout] = useState<Workout | null>(null);
  const [metrics, setMetrics] = useState<HRZonesResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([api.getWorkout(id), api.getWorkoutMetrics(id)])
      .then(([w, m]) => {
        setWorkout(w);
        setMetrics(m);
      })
      .catch((e) => setError(String(e)));
  }, [id]);

  if (error) return <p className="muted">No se pudo cargar: {error}</p>;
  if (!workout || !metrics) return <p className="muted">Cargando...</p>;

  if (workout.type === "cardio") return <CardioView workout={workout} metrics={metrics} />;
  return <StrengthView workout={workout} onSaved={setWorkout} />;
}

function CardioView({ workout, metrics }: { workout: Workout; metrics: HRZonesResponse }) {
  const pace = workout.cardio_detail?.avg_pace_s_per_km;
  const distance = workout.cardio_detail?.distance_m;
  const paceStr = pace
    ? `${Math.floor(pace / 60)}:${String(Math.round(pace % 60)).padStart(2, "0")} /km`
    : "—";
  return (
    <div>
      <h1>Cardio</h1>
      <p className="muted small">{new Date(workout.start_time).toLocaleString()}</p>
      <div className="card">
        <p>
          Duración: <strong>{Math.round(workout.duration_s / 60)} min</strong> · Distancia:{" "}
          <strong>{distance != null ? `${(distance / 1000).toFixed(2)} km` : "—"}</strong> · Pace:{" "}
          <strong>{paceStr}</strong>
        </p>
        {workout.avg_hr && <p>FC media: {workout.avg_hr} bpm (máx {workout.max_hr ?? "—"})</p>}
        {workout.calories && <p>Calorías: {workout.calories}</p>}
      </div>
      <h2>Zonas de FC</h2>
      <p className="muted small">hr_max = {metrics.hr_max_bpm} bpm</p>
      <table>
        <thead>
          <tr>
            <th>Zona</th>
            <th>Rango</th>
            <th>Tiempo</th>
          </tr>
        </thead>
        <tbody>
          {metrics.zones.map((z) => (
            <tr key={z.zone}>
              <td>Z{z.zone}</td>
              <td>
                {z.lower_bpm}–{z.upper_bpm} bpm
              </td>
              <td>{Math.round(z.seconds_in_zone / 60)} min</td>
            </tr>
          ))}
        </tbody>
      </table>
      <h2>Mapa</h2>
      <div className="card">
        <p className="muted small">
          Polyline: <code>{workout.cardio_detail?.gps_polyline ?? "—"}</code>
        </p>
        <p className="muted small">
          (Integración de mapa pendiente — la polyline está lista para enviarse a un proveedor
          como Leaflet o Mapbox.)
        </p>
      </div>
    </div>
  );
}

function StrengthView({
  workout,
  onSaved,
}: {
  workout: Workout;
  onSaved: (w: Workout) => void;
}) {
  const [editing, setEditing] = useState(workout.exercises.length === 0);
  return (
    <div>
      <h1>Fuerza</h1>
      <p className="muted small">{new Date(workout.start_time).toLocaleString()}</p>
      <div className="card">
        <p>
          Duración: <strong>{Math.round(workout.duration_s / 60)} min</strong>
        </p>
        {workout.strength_total_volume_kg != null && (
          <p>
            Volumen: <strong>{workout.strength_total_volume_kg.toFixed(1)} kg</strong>
          </p>
        )}
        {workout.strength_total_sets != null && <p>Series: {workout.strength_total_sets}</p>}
        {workout.strength_exercises_count != null && (
          <p>Ejercicios: {workout.strength_exercises_count}</p>
        )}
      </div>

      <h2>Registro</h2>
      {editing ? (
        <StrengthLogForm
          workout={workout}
          onSaved={(w) => {
            onSaved(w);
            setEditing(false);
          }}
          onCancel={workout.exercises.length > 0 ? () => setEditing(false) : undefined}
        />
      ) : (
        <>
          {workout.exercises.map((e) => (
            <div className="card" key={e.id}>
              <strong>{e.name}</strong>
              <table>
                <thead>
                  <tr>
                    <th>Serie</th>
                    <th>Reps</th>
                    <th>Peso</th>
                  </tr>
                </thead>
                <tbody>
                  {e.sets.map((s) => (
                    <tr key={s.id}>
                      <td>{s.order_index}</td>
                      <td>{s.reps}</td>
                      <td>{s.weight_kg} kg</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ))}
          <button type="button" onClick={() => setEditing(true)}>
            Editar registro
          </button>
        </>
      )}
    </div>
  );
}

const CUSTOM = "";

interface DraftExercise {
  key: string; // catalog key, or CUSTOM for a free-text exercise
  name: string;
  sets: SetIn[];
}

function draftsFrom(workout: Workout): DraftExercise[] {
  if (workout.exercises.length === 0) {
    return [{ key: CUSTOM, name: "", sets: [{ reps: 5, weight_kg: 0 }] }];
  }
  return workout.exercises.map((e) => ({
    key: e.exercise_key ?? CUSTOM,
    name: e.name,
    sets: e.sets.map((s) => ({ reps: s.reps, weight_kg: s.weight_kg })),
  }));
}

function StrengthLogForm({
  workout,
  onSaved,
  onCancel,
}: {
  workout: Workout;
  onSaved: (w: Workout) => void;
  onCancel?: () => void;
}) {
  const [catalog, setCatalog] = useState<CatalogExercise[]>([]);
  const [drafts, setDrafts] = useState<DraftExercise[]>(() => draftsFrom(workout));
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.listExercises().then(setCatalog).catch(() => setCatalog([]));
  }, []);

  function update(i: number, change: (d: DraftExercise) => DraftExercise) {
    setDrafts((all) => all.map((d, j) => (j === i ? change(d) : d)));
  }

  function setField(i: number, j: number, field: "reps" | "weight_kg", value: number) {
    update(i, (d) => ({
      ...d,
      sets: d.sets.map((s, k) => (k === j ? { ...s, [field]: value } : s)),
    }));
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const saved = await api.replaceExercises(
        workout.id,
        drafts.map((d) =>
          d.key === CUSTOM
            ? { name: d.name.trim(), sets: d.sets }
            : { exercise_key: d.key, sets: d.sets },
        ),
      );
      onSaved(saved);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit}>
      {drafts.map((d, i) => (
        <div className="card" key={i}>
          <label>Ejercicio</label>
          <select
            value={d.key}
            onChange={(e) => {
              const key = e.target.value;
              const name = catalog.find((c) => c.key === key)?.name ?? "";
              update(i, (x) => ({ ...x, key, name }));
            }}
          >
            {catalog.map((c) => (
              <option key={c.key} value={c.key}>
                {c.name}
              </option>
            ))}
            <option value={CUSTOM}>Otro (escribir nombre)</option>
          </select>
          {d.key === CUSTOM && (
            <input
              placeholder="Nombre del ejercicio"
              value={d.name}
              onChange={(e) => update(i, (x) => ({ ...x, name: e.target.value }))}
              required
            />
          )}
          <table>
            <thead>
              <tr>
                <th>Serie</th>
                <th>Reps</th>
                <th>Peso (kg)</th>
              </tr>
            </thead>
            <tbody>
              {d.sets.map((s, j) => (
                <tr key={j}>
                  <td>{j + 1}</td>
                  <td>
                    <input
                      type="number"
                      min={0}
                      value={s.reps}
                      onChange={(e) => setField(i, j, "reps", Number(e.target.value))}
                      required
                    />
                  </td>
                  <td>
                    <input
                      type="number"
                      min={0}
                      step={0.5}
                      value={s.weight_kg}
                      onChange={(e) => setField(i, j, "weight_kg", Number(e.target.value))}
                      required
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="row">
            <button
              type="button"
              className="secondary"
              onClick={() => update(i, (x) => ({ ...x, sets: [...x.sets, { ...x.sets[x.sets.length - 1] }] }))}
            >
              + Serie
            </button>
            <button
              type="button"
              className="secondary"
              disabled={d.sets.length === 1}
              onClick={() => update(i, (x) => ({ ...x, sets: x.sets.slice(0, -1) }))}
            >
              − Serie
            </button>
            <button
              type="button"
              className="secondary"
              disabled={drafts.length === 1}
              onClick={() => setDrafts((all) => all.filter((_, j) => j !== i))}
            >
              Quitar ejercicio
            </button>
          </p>
        </div>
      ))}
      <p className="row">
        <button
          type="button"
          className="secondary"
          onClick={() =>
            setDrafts((all) => [...all, { key: CUSTOM, name: "", sets: [{ reps: 5, weight_kg: 0 }] }])
          }
        >
          + Ejercicio
        </button>
        <button type="submit" disabled={busy}>
          {busy ? "Guardando..." : "Guardar"}
        </button>
        {onCancel && (
          <button type="button" className="secondary" onClick={onCancel}>
            Cancelar
          </button>
        )}
      </p>
      {error && <p style={{ color: "var(--danger)" }}>Error: {error}</p>}
    </form>
  );
}
