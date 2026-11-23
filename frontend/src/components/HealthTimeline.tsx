"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { HealthCoverage, HealthKind, TimelinePage } from "@/lib/types";
import styles from "./HealthTimeline.module.css";

const categories: Record<HealthKind, string> = {
  heart_rate: "Frecuencia cardiaca", body_mass: "Peso corporal", sleep: "Sueño", workout: "Entrenamientos",
};
const values: Record<string, string> = {
  in_bed: "En cama", awake: "Despierto", asleep: "Dormido", core: "Sueño esencial", deep: "Sueño profundo",
  rem: "Sueño REM", unknown: "Desconocido", strength: "Fuerza", walk: "Caminata", run: "Carrera", other: "Otro",
};
const time = new Intl.DateTimeFormat("es-CO", { hour: "2-digit", minute: "2-digit", hourCycle: "h23" });
const fullTime = new Intl.DateTimeFormat("es-CO", {
  day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit", second: "2-digit",
  hourCycle: "h23", timeZoneName: "shortOffset",
});
const number = new Intl.NumberFormat("es-CO", { maximumFractionDigits: 6 });
const PAGE_SIZE = 200;

function localDay(date: Date): string {
  return [date.getFullYear(), String(date.getMonth() + 1).padStart(2, "0"), String(date.getDate()).padStart(2, "0")].join("-");
}

function TimelineChart({ samples, kind, start, end }: {
  samples: TimelinePage["samples"]; kind: HealthKind; start: string; end: string;
}) {
  const isMeasurement = kind === "heart_rate" || kind === "body_mass";
  const unit = kind === "heart_rate" ? "lpm" : "kg";
  const first = Date.parse(start);
  const last = Date.parse(end);
  const left = isMeasurement ? 75 : 130;
  const right = 690;
  const x = (at: number) => left + (Math.min(last, Math.max(first, at)) - first) / (last - first) * (right - left);
  const quantities = samples.flatMap((s) => typeof s.value === "number" ? [s.value] : []);
  const lanes = Array.from(new Set(samples.flatMap((s) => typeof s.value === "string" ? [s.value] : [])));
  const min = quantities.length ? Math.min(...quantities) : 0;
  const max = quantities.length ? Math.max(...quantities) : 0;
  const y = (value: number) => max === min ? 70 : 120 - (value - min) * 100 / (max - min);
  const baseline = isMeasurement ? 140 : 20 + lanes.length * 28;
  const ticks = [first, ...[6, 12, 18].map((hour) => {
    const tick = new Date(first);
    return tick.setHours(hour, 0, 0, 0);
  }), last];

  return <div className={styles.chart}>
    <svg viewBox={`0 0 725 ${baseline + 28}`} role="img"
      aria-label={`${categories[kind]} por hora. ${samples.length} muestras en esta página. La tabla contiene los valores.`}>
      {ticks.map((tick) => <g key={tick}>
        <line x1={x(tick)} x2={x(tick)} y1={10} y2={baseline} className={styles.grid} />
        <text x={x(tick)} y={baseline + 18} textAnchor="middle">{time.format(tick)}</text>
      </g>)}
      {isMeasurement ? Array.from(new Set([min, max])).map((value) =>
        <text key={value} x={left - 8} y={y(value) + 4} textAnchor="end">{number.format(value)} {unit}</text>
      ) : lanes.map((lane, i) =>
        <text key={lane} x={left - 8} y={24 + i * 28} textAnchor="end">{values[lane] ?? lane}</text>
      )}
      {samples.map((s) => {
        const at = x(Date.parse(s.start));
        if (typeof s.value === "number") {
          return <circle key={s.sample_id} cx={at} cy={y(s.value)} r="3" className={styles.point} />;
        }
        const row = 20 + lanes.indexOf(s.value) * 28;
        const until = x(Date.parse(s.end));
        return until === at ? <circle key={s.sample_id} cx={at} cy={row} r="3" className={styles.point} />
          : <line key={s.sample_id} x1={at} x2={until} y1={row} y2={row} className={styles.interval} />;
      })}
    </svg>
  </div>;
}

function TimelineResults({ kind, source, start, end }: {
  kind: HealthKind; source: string; start: string; end: string;
}) {
  const [offset, setOffset] = useState(0);
  const [attempt, setAttempt] = useState(0);
  const [page, setPage] = useState<TimelinePage>();
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    let active = true;
    api.healthTimeline({ kind, source, start, end, offset }).then((result) => {
      if (active) setPage(result);
    }).catch(() => { if (active) setFailed(true); });
    return () => { active = false; };
  }, [kind, source, start, end, offset, attempt]);

  function navigate(next: number) {
    setPage(undefined);
    setFailed(false);
    setOffset(next);
  }

  if (failed) return <div role="alert"><p>No se pudieron consultar las muestras.</p>
    <button onClick={() => { setFailed(false); setAttempt(attempt + 1); }}>Reintentar</button></div>;
  if (!page) return <p role="status">Consultando muestras…</p>;
  return <>
    {page.samples.length > 0 ? <>
      <p className="muted small">Muestras {offset + 1}–{offset + page.samples.length} · {new Intl.DateTimeFormat().resolvedOptions().timeZone}</p>
      <TimelineChart samples={page.samples} kind={kind} start={start} end={end} />
      <details className={styles.details}>
        <summary>Ver tabla de muestras</summary>
        <div className={styles.scroll}><table>
          <thead><tr><th scope="col">Inicio</th><th scope="col">Fin</th><th scope="col">Valor</th></tr></thead>
          <tbody>{page.samples.map((s) => <tr key={s.sample_id}>
            <td><time dateTime={s.start}>{fullTime.format(Date.parse(s.start))}</time></td>
            <td><time dateTime={s.end}>{fullTime.format(Date.parse(s.end))}</time></td>
            <td>{typeof s.value === "number" ? `${number.format(s.value)} ${kind === "heart_rate" ? "lpm" : "kg"}` : (values[s.value] ?? s.value)}</td>
          </tr>)}</tbody>
        </table></div>
      </details>
    </> : <p className="muted">Sin muestras de esta fuente para el día seleccionado.</p>}
    {(offset > 0 || page.has_more) && <div className="row">
      <button className="secondary" disabled={offset === 0} onClick={() => navigate(Math.max(0, offset - PAGE_SIZE))}>Página anterior</button>
      <button className="secondary" disabled={!page.has_more} onClick={() => navigate(offset + PAGE_SIZE)}>Página siguiente</button>
    </div>}
  </>;
}

export function HealthTimeline({ coverage }: { coverage: HealthCoverage[] }) {
  const [kind, setKind] = useState<HealthKind>("heart_rate");
  const [chosenSource, setSource] = useState("");
  const [chosenDay, setDay] = useState<string>();
  const available = coverage.filter((item) => item.sources.length > 0);
  const row = available.find((item) => item.kind === kind) ?? available[0];
  if (!row) return null;
  const source = row.sources.includes(chosenSource) ? chosenSource : row.sources[0];
  const latest = row.latest_by_source?.[source];
  const day = chosenDay ?? localDay(latest ? new Date(latest) : new Date());
  const first = new Date(`${day}T00:00:00`);
  const last = new Date(first.getFullYear(), first.getMonth(), first.getDate() + 1);
  const valid = /^\d{4}-\d{2}-\d{2}$/.test(day) && Number.isFinite(first.getTime()) && localDay(first) === day;
  return <section className={styles.timeline} aria-label="Historial diario de Salud">
    <h3>Historial diario</h3>
    <div className={styles.controls}>
      <label>Categoría<select value={row.kind} onChange={(e) => {
        setKind(e.target.value as HealthKind); setSource(""); setDay(undefined);
      }}>{available.map((item) => <option key={item.kind} value={item.kind}>{categories[item.kind]}</option>)}</select></label>
      <label>Fuente<select value={source} onChange={(e) => { setSource(e.target.value); setDay(undefined); }}>
        {row.sources.map((name) => <option key={name}>{name}</option>)}
      </select></label>
      <label>Día local<input type="date" value={day} onChange={(e) => setDay(e.target.value)} /></label>
    </div>
    {valid ? <TimelineResults key={JSON.stringify([row.kind, source, day])} kind={row.kind} source={source}
      start={first.toISOString()} end={last.toISOString()} /> : <p>Selecciona un día para consultar el historial.</p>}
  </section>;
}
