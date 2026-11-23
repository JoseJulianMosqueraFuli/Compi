"use client";

import { useRef, useState, type FormEvent } from "react";
import { api } from "@/lib/api";
import type { Availability, TimeWindow } from "@/lib/types";
import { formatDay } from "./WeeklyRecommendation";
import styles from "./week.module.css";

const days = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"];

export function AvailabilityEditor({ initial, today, onSaved }: {
  initial: Availability; today: string; onSaved: () => void;
}) {
  const [windows, setWindows] = useState(initial.windows);
  const [exceptions, setExceptions] = useState(initial.exceptions);
  const [exceptionDay, setExceptionDay] = useState(today);
  const [blocked, setBlocked] = useState(true);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const nextId = useRef(-1);

  function edit(id: number, change: Partial<TimeWindow>) {
    setWindows((previous) => previous.map((w) => w.id === id ? { ...w, ...change } : w));
    setMessage("");
  }

  async function save(operation: () => Promise<Availability>, success: string, replaceWindows = false) {
    setError(""); setMessage(""); setBusy(true);
    try {
      const saved = await operation();
      if (replaceWindows) setWindows(saved.windows);
      setExceptions(saved.exceptions);
      setMessage(success);
      onSaved();
    } catch (cause) {
      setError(String(cause));
    } finally {
      setBusy(false);
    }
  }

  function saveWindows(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const rows = windows.map(({ weekday, start_time, end_time, gym_access }) =>
      ({ weekday, start_time, end_time, gym_access }));
    void save(() => api.saveWindows(rows), "Horario semanal guardado.", true);
  }

  function addException(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const start = blocked ? null : String(data.get("start"));
    const end = blocked ? null : String(data.get("end"));
    if (start && end && start >= end) {
      setError("La hora final debe ser posterior a la inicial."); return;
    }
    const overlaps = exceptions.some((ex) => ex.day === exceptionDay && (
      !start || !end || !ex.start_time || !ex.end_time ||
      (start.slice(0, 5) < ex.end_time.slice(0, 5) && ex.start_time.slice(0, 5) < end.slice(0, 5))
    ));
    if (overlaps) {
      setError("Ya hay una excepción en ese horario. Quita la anterior para sustituirla."); return;
    }
    void save(() => api.addException({
      day: exceptionDay, start_time: start, end_time: end, gym_access: !blocked && data.has("gym"), note: null,
    }), "Excepción guardada.");
  }

  return <section className="card">
    <h2>Disponibilidad</h2>
    <p className="muted">La fuerza requiere una franja con acceso al gimnasio.</p>
    <form onSubmit={saveWindows}>
      <fieldset className={styles.fields} disabled={busy}>
        <legend>Horario semanal habitual</legend>
        {windows.length === 0 && <p>Añade los horarios en los que puedes entrenar.</p>}
        {windows.map((w) => <div className={styles.window} key={w.id}>
          <label>Día<select value={w.weekday} onChange={(e) => edit(w.id, { weekday: Number(e.target.value) })}>
            {days.map((d, i) => <option key={d} value={i}>{d}</option>)}
          </select></label>
          <label>Desde<input required step="any" type="time" value={w.start_time} onChange={(e) => edit(w.id, { start_time: e.target.value })} /></label>
          <label>Hasta<input required step="any" type="time" value={w.end_time} onChange={(e) => edit(w.id, { end_time: e.target.value })} /></label>
          <label className={styles.check}><input type="checkbox" checked={w.gym_access} onChange={(e) => edit(w.id, { gym_access: e.target.checked })} /> Gimnasio</label>
          <button type="button" className="secondary" aria-label={`Quitar franja de ${days[w.weekday]} ${w.start_time}`} onClick={() => {
            setWindows(windows.filter((other) => other.id !== w.id)); setMessage("");
          }}>Quitar</button>
        </div>)}
        <div className="row"><button type="button" className="secondary" onClick={() => {
          setWindows([...windows, { id: nextId.current--, weekday: 0, start_time: "07:00", end_time: "08:00", gym_access: false }]);
          setMessage("");
        }}>Añadir franja</button><button type="submit">Guardar horario</button></div>
      </fieldset>
    </form>
    <details className={styles.subsection}>
      <summary>Excepciones por fecha</summary>
      <p className="muted">En esa fecha se aplican las excepciones que registres en lugar del horario habitual.</p>
      {exceptions.map((ex) => <div key={ex.id} className={styles.exception}>
        <span>{formatDay(ex.day)} · {ex.start_time && ex.end_time ? `${ex.start_time.slice(0, 5)}–${ex.end_time.slice(0, 5)}` : "Día sin disponibilidad"}
          {ex.gym_access && " · Gimnasio"}{ex.note && ` · ${ex.note}`}</span>
        <button type="button" disabled={busy} className="secondary" onClick={() =>
          void save(() => api.deleteException(ex.id), "Excepción eliminada.")
        }>Quitar excepción</button>
      </div>)}
      <form onSubmit={addException}>
        <fieldset className={styles.fields} disabled={busy}>
          <label>Fecha<input type="date" required value={exceptionDay} onChange={(e) => setExceptionDay(e.target.value)} /></label>
          <label className={styles.check}><input type="checkbox" checked={blocked} onChange={(e) => setBlocked(e.target.checked)} /> Día sin disponibilidad</label>
          {!blocked && <div className={styles.window}>
            <label>Desde<input required name="start" type="time" /></label>
            <label>Hasta<input required name="end" type="time" /></label>
            <label className={styles.check}><input type="checkbox" name="gym" /> Gimnasio</label>
          </div>}
          <button type="submit">Añadir excepción</button>
        </fieldset>
      </form>
    </details>
    {error && <p role="alert">{error}</p>}
    {message && <p role="status">{message}</p>}
  </section>;
}
