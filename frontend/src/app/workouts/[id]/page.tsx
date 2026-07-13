"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { api } from "@/lib/api";
import type { HRZonesResponse, Workout } from "@/lib/types";

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
  return <StrengthView workout={workout} />;
}

function CardioView({ workout, metrics }: { workout: Workout; metrics: HRZonesResponse }) {
  const pace = workout.cardio_detail?.avg_pace_s_per_km;
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
          <strong>—</strong> · Pace: <strong>{paceStr}</strong>
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

function StrengthView({ workout }: { workout: Workout }) {
  return <StrengthDetailForm workout={workout} />;
}

function StrengthDetailForm({ workout }: { workout: Workout }) {
  const [exercise, setExercise] = useState("Squat");
  const [sets, setSets] = useState(5);
  const [reps, setReps] = useState(5);
  const [weight, setWeight] = useState(100);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api.attachStrengthDetail(workout.id, {
        exercise,
        sets,
        reps,
        weight_kg: weight,
      });
      setSaved(true);
    } catch (err) {
      setError(String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <h1>Fuerza</h1>
      <p className="muted small">{new Date(workout.start_time).toLocaleString()}</p>
      <div className="card">
        <p>
          Duración: <strong>{Math.round(workout.duration_s / 60)} min</strong>
        </p>
        {workout.strength_total_volume_kg && (
          <p>Volumen: <strong>{workout.strength_total_volume_kg.toFixed(1)} kg</strong></p>
        )}
        {workout.strength_total_sets && <p>Series: {workout.strength_total_sets}</p>}
        {workout.strength_exercises_count && <p>Ejercicios: {workout.strength_exercises_count}</p>}
      </div>

      <h2>Registro manual</h2>
      {workout.strength_detail ? (
        <p className="muted">
          Ya registrado: {workout.strength_detail.exercise} —{" "}
          {workout.strength_detail.sets}×{workout.strength_detail.reps} @{" "}
          {workout.strength_detail.weight_kg} kg
        </p>
      ) : (
        <form onSubmit={submit} className="card">
          <label>Ejercicio</label>
          <input value={exercise} onChange={(e) => setExercise(e.target.value)} required />
          <label>Series</label>
          <input
            type="number"
            min={1}
            value={sets}
            onChange={(e) => setSets(Number(e.target.value))}
            required
          />
          <label>Repeticiones</label>
          <input
            type="number"
            min={1}
            value={reps}
            onChange={(e) => setReps(Number(e.target.value))}
            required
          />
          <label>Peso (kg)</label>
          <input
            type="number"
            min={0}
            step={0.5}
            value={weight}
            onChange={(e) => setWeight(Number(e.target.value))}
            required
          />
          <p style={{ marginTop: "1rem" }}>
            <button type="submit" disabled={busy}>
              {busy ? "Guardando..." : "Guardar"}
            </button>
          </p>
          {saved && <p style={{ color: "var(--success)" }}>Guardado.</p>}
          {error && <p style={{ color: "var(--danger)" }}>Error: {error}</p>}
        </form>
      )}
    </div>
  );
}
