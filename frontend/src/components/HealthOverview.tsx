"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { DurationEvaluation, HealthCoverage, HealthKind } from "@/lib/types";

const names: Record<HealthKind, string> = {
  workout: "Entrenamientos", heart_rate: "Frecuencia cardiaca", sleep: "Sueño", body_mass: "Peso corporal",
};

export function HealthOverview() {
  const [coverage, setCoverage] = useState<HealthCoverage[]>();
  const [source, setSource] = useState("");
  const [evaluation, setEvaluation] = useState<DurationEvaluation>();
  const [failed, setFailed] = useState(false);
  const [evaluationFailed, setEvaluationFailed] = useState(false);

  useEffect(() => {
    let active = true;
    api.healthCoverage().then((rows) => {
      if (!active) return;
      setCoverage(rows);
      setSource(rows.find((row) => row.kind === "workout")?.sources[0] ?? "");
    }).catch(() => { if (active) setFailed(true); });
    return () => { active = false; };
  }, []);

  useEffect(() => {
    let active = true;
    if (source) {
      api.evaluateDuration(source).then((result) => {
        if (active) setEvaluation(result);
      }).catch(() => { if (active) setEvaluationFailed(true); });
    }
    return () => { active = false; };
  }, [source]);

  const sources = coverage?.find((item) => item.kind === "workout")?.sources ?? [];
  return (
    <section className="card">
      <h2>Datos de Salud del iPhone</h2>
      {failed && <p role="alert">No se pudo consultar la sincronización.</p>}
      {!coverage && !failed && <p>Cargando estado…</p>}
      {coverage && (
        <table>
          <thead><tr><th>Categoría</th><th>Muestras</th><th>Último lote recibido</th></tr></thead>
          <tbody>{coverage.map((item) => (
            <tr key={item.kind}>
              <th scope="row">{names[item.kind]}</th><td>{item.samples}</td>
              <td>{item.last_batch ? new Date(item.last_batch).toLocaleString("es-CO") : "Sin lotes recibidos"}</td>
            </tr>
          ))}</tbody>
        </table>
      )}
      {coverage?.every((item) => !item.last_batch) &&
        <p className="muted">Abre Compi en el iPhone y sincroniza las categorías que quieras compartir.</p>}
      {sources.length > 0 && <>
        <h3>Duración de las sesiones</h3>
        <label htmlFor="workout-source">Fuente de entrenamientos</label>
        <select id="workout-source" value={source} onChange={(event) => {
          setEvaluation(undefined); setEvaluationFailed(false); setSource(event.target.value);
        }}>{sources.map((name) => <option key={name}>{name}</option>)}</select>
        {evaluationFailed && <p role="alert">No se pudo evaluar esta fuente.</p>}
        {!evaluation && !evaluationFailed && <p>Cargando comparación…</p>}
        {evaluation && (evaluation.baseline && evaluation.by_activity ? <>
          <p>Error medio al estimar los minutos entre el inicio y el fin de {evaluation.evaluated_sessions} sesiones.</p>
          <table>
            <thead><tr><th>Referencia</th><th>Error absoluto</th><th>Duraciones subestimadas</th></tr></thead>
            <tbody>
              <tr><td>Historial general</td><td>{evaluation.baseline.mae_minutes} min</td><td>{evaluation.baseline.underestimated}</td></tr>
              <tr><td>Misma actividad</td><td>{evaluation.by_activity.mae_minutes} min</td><td>{evaluation.by_activity.underestimated}</td></tr>
            </tbody>
          </table>
        </> : <p className="muted">Hay {evaluation.observed_sessions} sesiones de fuerza, caminata o carrera.
          Para evaluar una sesión hacen falta tres anteriores de esa misma actividad.</p>)}
      </>}
    </section>
  );
}
