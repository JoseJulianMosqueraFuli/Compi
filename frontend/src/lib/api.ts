import type {
  Availability,
  DateException,
  CatalogExercise,
  DurationEvaluation,
  ExerciseIn,
  HealthCoverage,
  HRZonesResponse,
  Macrociclo,
  MetricsResponse,
  ProgressionResponse,
  RecommendedWeek,
  TimeWindow,
  TrainingPreferences,
  Workout,
  WorkoutType,
} from "./types";

const BASE_URL = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(/\/$/, "");

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

/** FastAPI puts a string in `detail`, or a list of validation errors for a 422. */
function describe(body: unknown, fallback: string): string {
  const detail = (body as { detail?: unknown } | null)?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((d: { loc?: unknown[]; msg?: string }) =>
        [d.loc?.slice(1).join("."), d.msg].filter(Boolean).join(": "),
      )
      .join("; ");
  }
  return fallback;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE_URL}${path}`, {
    ...init,
    cache: "no-store",
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    throw new ApiError(response.status, describe(body, `${response.status} ${response.statusText}`));
  }
  return body as T;
}

export const api = {
  healthCoverage: () => request<HealthCoverage[]>("/api/healthkit/coverage"),
  evaluateDuration: (source: string) => request<DurationEvaluation>("/api/healthkit/duration-evaluation", {
    method: "POST", body: JSON.stringify({ source }),
  }),
  listWorkouts: (params: { type?: WorkoutType; limit?: number; offset?: number } = {}) => {
    const query = new URLSearchParams();
    if (params.type) query.set("workout_type", params.type);
    if (params.limit !== undefined) query.set("limit", String(params.limit));
    if (params.offset !== undefined) query.set("offset", String(params.offset));
    const qs = query.toString();
    return request<Workout[]>(`/api/workouts${qs ? `?${qs}` : ""}`);
  },
  getWorkout: (id: number) => request<Workout>(`/api/workouts/${id}`),
  getWorkoutMetrics: (id: number) => request<HRZonesResponse>(`/api/workouts/${id}/metrics`),
  /** Replaces the whole strength log of the workout with these exercises and sets. */
  replaceExercises: (id: number, exercises: ExerciseIn[]) =>
    request<Workout>(`/api/workouts/${id}/exercises`, {
      method: "PUT",
      body: JSON.stringify(exercises),
    }),
  listExercises: () => request<CatalogExercise[]>("/api/exercises"),

  totalVolume: () => request<MetricsResponse>("/api/metrics/volume"),
  totalLoad: () => request<MetricsResponse>("/api/metrics/load"),

  listMacrocycles: () => request<Macrociclo[]>("/api/plans/macrocycles"),
  macrocicloProgression: (id: number) =>
    request<ProgressionResponse>(`/api/plans/${id}/progression`),
  availability: () => request<Availability>("/api/availability"),
  saveWindows: (windows: TimeWindow[]) => request<Availability>("/api/availability/windows", {
    method: "PUT", body: JSON.stringify(windows),
  }),
  addException: (exception: DateException) => request<Availability>("/api/availability/exceptions", {
    method: "POST", body: JSON.stringify(exception),
  }),
  deleteException: (id: number) => request<Availability>(`/api/availability/exceptions/${id}`, {
    method: "DELETE",
  }),
  preferences: () => request<TrainingPreferences>("/api/preferences"),
  savePreferences: (preferences: TrainingPreferences) => request<TrainingPreferences>("/api/preferences", {
    method: "PUT", body: JSON.stringify(preferences),
  }),
  week: (day: string) => request<RecommendedWeek>(`/api/recommendations/week?day=${encodeURIComponent(day)}`),
  generateWeek: (day: string, regenerate: boolean) => request<RecommendedWeek>("/api/recommendations/week", {
    method: "POST", body: JSON.stringify({ day, regenerate }),
  }),
};
