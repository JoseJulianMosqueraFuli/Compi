"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { Macrociclo, ProgressionResponse } from "@/lib/types";

export default function PlanPage() {
  const [macros, setMacros] = useState<Macrociclo[] | null>(null);
  const [selected, setSelected] = useState<number | null>(null);
  const [prog, setProg] = useState<ProgressionResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.listMacrocycles().then(setMacros).catch((e) => setError(String(e)));
  }, []);

  useEffect(() => {
    if (selected == null) {
      setProg(null);
      return;
    }
    api.macrocicloProgression(selected).then(setProg).catch((e) => setError(String(e)));
  }, [selected]);

  if (error) return <p className="muted">No se pudo cargar: {error}</p>;
  if (!macros) return <p className="muted">Cargando...</p>;

  return (
    <div>
      <h1>Plan</h1>
      {macros.length === 0 && <p className="muted">No hay macrociclos aún.</p>}
      {macros.map((m) => (
        <div key={m.id} className="card">
          <strong>{m.name}</strong>{" "}
          <span className="muted small">
            {m.start_date} → {m.end_date}
          </span>
          <p>
            <button onClick={() => setSelected(m.id)}>Ver progresión</button>
          </p>
        </div>
      ))}
      {prog && (
        <div className="card">
          <h2>Progresión del macrociclo #{prog.macrociclo_id}</h2>
          <table>
            <thead>
              <tr>
                <th>Microciclo</th>
                <th>Carga objetivo</th>
                <th>Deload</th>
              </tr>
            </thead>
            <tbody>
              {prog.points.map((p) => (
                <tr key={p.microciclo_id}>
                  <td>#{p.microciclo_id}</td>
                  <td>{p.target_load.toFixed(1)}</td>
                  <td>{p.is_deload ? "Sí" : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
