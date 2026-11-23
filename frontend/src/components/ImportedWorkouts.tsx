"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { ImportedWorkout, Workout } from "@/lib/types";

const activities = { strength: "Fuerza", walk: "Caminata", run: "Carrera", other: "Otra actividad" };

export function ImportedWorkouts({ source, registered, onConfirmed }: {
  source: string; registered: Workout[]; onConfirmed: () => void;
}) {
  const [rows, setRows] = useState<ImportedWorkout[]>();
  const [error, setError] = useState("");
  const [working, setWorking] = useState(false);
  const [choosing, setChoosing] = useState("");
  const [existing, setExisting] = useState("");

  useEffect(() => {
    let active = true;
    api.importedWorkouts(source).then((result) => { if (active) setRows(result); })
      .catch(() => { if (active) setError("No se pudieron cargar los entrenamientos importados."); });
    return () => { active = false; };
  }, [source]);

  async function confirm(sample: ImportedWorkout) {
    setWorking(true);
    setError("");
    try {
      const { workout_id } = await api.confirmWorkout(sample.sample_id, existing ? Number(existing) : null);
      setRows((previous) => previous?.map((r) => r.sample_id === sample.sample_id ? { ...r, workout_id } : r));
      setChoosing("");
      onConfirmed();
    } catch {
      setError("No se pudo vincular el entrenamiento. Revisa el registro elegido y vuelve a intentarlo.");
    } finally {
      setWorking(false);
    }
  }

  return <details className="health-imports">
    <summary>Entrenamientos importados{rows ? ` (${rows.length} más recientes)` : ""}</summary>
    {error && <p role="alert">{error}</p>}
    {rows?.map((sample) => {
      const candidates = registered.filter((w) => sample.activity === "strength" ? w.type === "strength" :
        w.type === "cardio" && (!w.subtype || w.subtype === sample.activity));
      const minutes = Math.round((Date.parse(sample.end) - Date.parse(sample.start)) / 60000);
      return <div className="import-row" key={sample.sample_id}>
        <div><strong>{activities[sample.activity]}</strong> · {new Date(sample.start).toLocaleString("es-CO")} · {minutes} min</div>
        {sample.workout_id ? <Link href={`/workouts/${sample.workout_id}`}>Abrir registro</Link> :
          sample.activity !== "other" && (choosing === sample.sample_id ? <fieldset disabled={working}>
            <legend>Confirmar en mi registro</legend>
            <label>Destino<select value={existing} onChange={(e) => setExisting(e.target.value)}>
              <option value="">Crear un entrenamiento con esta hora y duración</option>
              {candidates.map((w) => <option key={w.id} value={w.id}>
                Registro #{w.id} · {new Date(w.start_time).toLocaleString("es-CO")} · {Math.round(w.duration_s / 60)} min
              </option>)}
            </select></label>
            <p className="small muted">El registro confirmado conserva tus ediciones si la fuente cambia o elimina la muestra.</p>
            <div className="row">
              <button type="button" onClick={() => confirm(sample)}>Confirmar</button>
              <button type="button" className="secondary" onClick={() => setChoosing("")}>Cancelar</button>
            </div>
          </fieldset> : <button type="button" className="secondary" disabled={working}
            onClick={() => { setChoosing(sample.sample_id); setExisting(""); }}>Registrar o vincular</button>)}
      </div>;
    })}
  </details>;
}
