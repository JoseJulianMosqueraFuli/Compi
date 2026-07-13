"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import type { MetricsResponse, Workout } from "@/lib/types";

export default function DashboardPage() {
  const [workouts, setWorkouts] = useState<Workout[] | null>(null);
  const [volume, setVolume] = useState<MetricsResponse | null>(null);
  const [load, setLoad] = useState<MetricsResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([api.listWorkouts(), api.totalVolume(), api.totalLoad()])
      .then(([w, v, l]) => {
        setWorkouts(w);
        setVolume(v);
        setLoad(l);
      })
      .catch((e) => setError(String(e)));
  }, []);

  if (error) {
    return <p className="muted">No se pudo cargar: {error}</p>;
  }
  if (!workouts || !volume || !load) {
    return <p className="muted">Cargando...</p>;
  }

  const recent = workouts.slice(0, 5);
  return (
    <div>
      <h1>Compi</h1>
      <p className="muted">Resumen de tus entrenamientos.</p>

      <div className="card">
        <h2>Métricas agregadas</h2>
        <p>
          Volumen total: <strong>{volume.total.toFixed(1)}</strong> kg/min
        </p>
        <p>
          Carga total: <strong>{load.total.toFixed(1)}</strong>
        </p>
      </div>

      <h2>Últimos entrenamientos</h2>
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
