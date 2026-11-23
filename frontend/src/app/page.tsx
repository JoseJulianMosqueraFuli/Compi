"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { HealthOverview } from "@/components/HealthOverview";
import { api } from "@/lib/api";
import type { Workout } from "@/lib/types";

export default function DashboardPage() {
  const [workouts, setWorkouts] = useState<Workout[] | null>(null);
  const [totals, setTotals] = useState<Awaited<ReturnType<typeof api.activityTotals>> | null>(null);
  const [error, setError] = useState<string | null>(null);

  const loadDashboard = useCallback(() => {
    Promise.all([api.listWorkouts(), api.activityTotals()])
      .then(([w, data]) => {
        setWorkouts(w);
        setTotals(data);
      })
      .catch((e) => setError(String(e)));
  }, []);
  useEffect(loadDashboard, [loadDashboard]);

  if (error) {
    return <p className="muted">No se pudo cargar: {error}</p>;
  }
  if (!workouts || !totals) {
    return <p className="muted">Cargando...</p>;
  }

  const recent = workouts.slice(0, 5);
  return (
    <div>
      <h1>Compi</h1>
      <p className="muted">Resumen de tus entrenamientos.</p>
      <HealthOverview registered={workouts} onConfirmed={loadDashboard} />

      <div className="card">
        <h2>Entrenamiento registrado</h2>
        <p>Volumen de fuerza · <strong>{totals.strength_kg === null ? "Sin datos" : `${totals.strength_kg.toFixed(1)} kg`}</strong></p>
        <p>Tiempo de cardio · <strong>{totals.cardio_minutes === null ? "Sin datos" : `${Math.round(totals.cardio_minutes)} min`}</strong></p>
        {totals.estimated_load !== null && <p>Carga estimada · <strong>{totals.estimated_load.toFixed(1)}</strong> sobre {totals.sessions_with_avg_hr} sesiones con FC media registrada.</p>}
      </div>

      <h2>Últimos entrenamientos registrados</h2>
      {recent.length === 0 && <p className="muted">Sin entrenamientos aún.</p>}
      {recent.map((w) => (
        <Link key={w.id} href={`/workouts/${w.id}`}>
          <div className="card">
            <strong>{w.type === "cardio" ? "Cardio" : "Fuerza"}</strong>{" "}
            <span className="muted small">
              {new Date(w.start_time).toLocaleString()} · {Math.round(w.duration_s / 60)} min
            </span>
            {w.avg_hr && <p className="small muted">FC media: {w.avg_hr} bpm</p>}
          </div>
        </Link>
      ))}
    </div>
  );
}
