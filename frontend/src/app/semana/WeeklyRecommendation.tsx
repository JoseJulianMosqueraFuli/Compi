"use client";

import { useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import type { RecommendedWeek } from "@/lib/types";
import styles from "./week.module.css";

const statuses = { pending: "Pendiente", done: "Completada", partial: "Parcial", skipped: "Omitida" };
const dateFormat = new Intl.DateTimeFormat("es-CO", { day: "numeric", month: "short", weekday: "short", timeZone: "UTC" });

export function formatDay(day: string) {
  return dateFormat.format(new Date(`${day}T12:00:00Z`));
}

export function WeeklyRecommendation({ day }: { day: string }) {
  const [week, setWeek] = useState<RecommendedWeek | null>();
  const [working, setWorking] = useState(false);
  const [error, setError] = useState("");
  const [reload, setReload] = useState(0);

  useEffect(() => {
    let active = true;
    api.week(day).then((value) => { if (active) setWeek(value); }).catch((cause) => {
      if (!active) return;
      if (cause instanceof ApiError && cause.status === 404) setWeek(null);
      else setError(String(cause));
    });
    return () => { active = false; };
  }, [day, reload]);

  async function generate() {
    setWorking(true);
    setError("");
    try {
      setWeek(await api.generateWeek(day, Boolean(week)));
    } catch (cause) {
      setError(String(cause));
    } finally {
      setWorking(false);
    }
  }

  return <>
    {error && <p role="alert">{error}</p>}
    {week === undefined && (error ?
      <button type="button" onClick={() => { setError(""); setReload(reload + 1); }}>Volver a cargar</button> :
      <p role="status">Consultando esta semana…</p>)}
    {week === null && <p>Todavía no has generado una recomendación para esta semana.</p>}
    {week !== undefined && <button type="button" disabled={working} onClick={generate}>
      {working ? "Generando…" : week ? "Regenerar sesiones pendientes" : "Generar semana"}
    </button>}
    {week && <>
      <h3 className={styles.dateRange}>{formatDay(week.week_start)} – {formatDay(week.week_end)}</h3>
      {!week.sessions.length && <p>La semana está vacía. Revisa las sesiones por semana en tus preferencias.</p>}
      {week.sessions.map((s) => <article key={s.id} className={styles.session}>
        <h4>{s.title}</h4>
        <p>{s.day ? formatDay(s.day) : "Sin horario disponible"}
          {s.start_time && s.end_time && ` · ${s.start_time.slice(0, 5)}–${s.end_time.slice(0, 5)}`}
          {` · ${s.planned_minutes ?? s.full_minutes} min · ${statuses[s.status]}`}</p>
        {s.prescription.guidance && <p>{s.prescription.guidance}</p>}
        {s.prescription.exercises.length > 0 && <details>
          <summary>Ejercicios y series</summary>
          {s.prescription.exercises.map((exercise) => <div key={exercise.key}>
            <strong>{exercise.name}</strong>
            <ol>{exercise.sets.map((set, index) => <li key={index}>
              {set.reps} rep.{set.weight_kg !== null && ` · ${set.weight_kg} kg`} · {set.rest_s} s de descanso
            </li>)}</ol>
          </div>)}
        </details>}
        {s.reasons.length > 0 && <details>
          <summary>Motivos de la recomendación</summary>
          <ul>{s.reasons.map((reason, index) => <li key={index}>{reason}</li>)}</ul>
        </details>}
      </article>)}
    </>}
  </>;
}
