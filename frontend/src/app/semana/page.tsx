"use client";

import { useEffect, useState, type FormEvent } from "react";
import { api } from "@/lib/api";
import type { Availability, TrainingPreferences } from "@/lib/types";
import { AvailabilityEditor } from "./AvailabilityEditor";
import { WeeklyRecommendation } from "./WeeklyRecommendation";
import styles from "./week.module.css";

const activities = [
  { key: "strength", label: "Fuerza", maxSessions: 4, minMinutes: 20, maxMinutes: 150 },
  { key: "run", label: "Carrera", maxSessions: 4, minMinutes: 10, maxMinutes: 120 },
  { key: "walk", label: "Caminata", maxSessions: 7, minMinutes: 10, maxMinutes: 180 },
] as const;

function todayIn(zone: string) {
  try {
    const parts = new Intl.DateTimeFormat("en-US", {
      timeZone: zone, year: "numeric", month: "2-digit", day: "2-digit",
    }).formatToParts(new Date());
    const fields = Object.fromEntries(parts.map(({ type, value }) => [type, value]));
    return `${fields.year}-${fields.month}-${fields.day}`;
  } catch {
    // The backend can have newer time-zone rules than an older browser.
    return "";
  }
}

function PreferencesEditor({ preferences, onSaved }: {
  preferences: TrainingPreferences; onSaved: (saved: TrainingPreferences) => void;
}) {
  const [zone, setZone] = useState(preferences.timezone);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const draft = { ...preferences, timezone: zone.trim() };
    for (const { key } of activities) {
      const count = `${key}_sessions_per_week` as const;
      const minutes = `${key}_minutes` as const;
      draft[count] = Number(data.get(count));
      draft[minutes] = Number(data.get(minutes));
    }
    setError(""); setMessage(""); setBusy(true);
    try {
      const saved = await api.savePreferences(draft);
      onSaved(saved);
      setMessage("Preferencias guardadas. Puedes regenerar las sesiones pendientes con estos valores.");
    } catch (cause) {
      setError(String(cause));
    } finally {
      setBusy(false);
    }
  }

  return <details className={`card ${styles.preferences}`}>
    <summary>Preferencias de entrenamiento</summary>
    <form onSubmit={save} onChange={() => setMessage("")}>
      <fieldset disabled={busy} className={styles.fields}>
        <label>Zona horaria<input list="training-zones" required value={zone} onChange={(e) => setZone(e.target.value)} /></label>
        <datalist id="training-zones"><option value="America/Bogota" /><option value="UTC" /></datalist>
        {zone !== "America/Bogota" && <button type="button" className="secondary" onClick={() => {
          setZone("America/Bogota"); setMessage("");
        }}>Usar horario de Bogotá</button>}
        {activities.map(({ key, label, maxSessions, minMinutes, maxMinutes }) => <div key={key} className={styles.activity}>
          <strong>{label}</strong>
          <label>Sesiones por semana<input type="number" required name={`${key}_sessions_per_week`} min="0" max={maxSessions} defaultValue={preferences[`${key}_sessions_per_week`]} /></label>
          <label>Minutos por sesión<input type="number" required name={`${key}_minutes`} min={minMinutes} max={maxMinutes} defaultValue={preferences[`${key}_minutes`]} /></label>
        </div>)}
        <button type="submit">Guardar preferencias</button>
      </fieldset>
    </form>
    {error && <p role="alert">{error}</p>}
    {message && <p role="status">{message}</p>}
  </details>;
}

export default function WeekPage() {
  const [preferences, setPreferences] = useState<TrainingPreferences>();
  const [availability, setAvailability] = useState<Availability>();
  const [selectedDay, setSelectedDay] = useState("");
  const [revision, setRevision] = useState(0);
  const [attempt, setAttempt] = useState(0);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    async function load() {
      try {
        const prefs = await api.preferences();
        if (!active) return;
        const windows = await api.availability();
        if (!active) return;
        setPreferences(prefs); setAvailability(windows);
      } catch (cause) {
        if (active) setError(String(cause));
      }
    }
    void load();
    return () => { active = false; };
  }, [attempt]);

  if (!preferences || !availability) return <>
    <h1>Mi semana</h1>
    {error ? <><p role="alert">{error}</p><button onClick={() => {
      setError(""); setAttempt(attempt + 1);
    }}>Volver a cargar</button></> : <p role="status">Cargando horarios y preferencias…</p>}
  </>;

  const today = todayIn(preferences.timezone);
  const day = selectedDay || today;
  return <div className={styles.planner}>
    <h1>Mi semana</h1>
    <section className="card">
      <h2>Recomendación semanal</h2>
      <label className={styles.datePicker}>Ver la semana del
        <input type="date" required value={day} onChange={(e) => setSelectedDay(e.target.value)} />
      </label>
      <p className="small muted">Horarios en {preferences.timezone}.</p>
      {day ? <WeeklyRecommendation key={`${day}-${revision}`} day={day} /> :
        <p>Selecciona una fecha para consultar la semana.</p>}
    </section>
    <AvailabilityEditor initial={availability} today={today} onSaved={() => setRevision((v) => v + 1)} />
    <PreferencesEditor preferences={preferences} onSaved={setPreferences} />
  </div>;
}
