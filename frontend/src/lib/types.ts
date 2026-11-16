// Mirrors of the backend response/request schemas (backend/app/routers/schemas.py and
// training_schemas.py). Keep in sync when those change.

export type WorkoutType = "cardio" | "strength";

export interface CardioDetail {
  id: number;
  gps_polyline: string | null;
  avg_pace_s_per_km: number | null;
  distance_m: number | null;
}

export interface ExerciseSet {
  id: number;
  order_index: number;
  reps: number;
  weight_kg: number;
  rest_s: number | null;
  rpe: number | null;
}

export interface WorkoutExercise {
  id: number;
  order_index: number;
  exercise_key: string | null;
  name: string;
  sets: ExerciseSet[];
}

export interface Workout {
  id: number;
  external_id: string;
  type: WorkoutType;
  subtype: string | null;
  start_time: string;
  duration_s: number;
  avg_hr: number | null;
  max_hr: number | null;
  calories: number | null;
  perceived_effort: number | null;
  notes: string | null;
  strength_total_volume_kg: number | null;
  strength_total_sets: number | null;
  strength_exercises_count: number | null;
  cardio_detail: CardioDetail | null;
  exercises: WorkoutExercise[];
}

/** One set as sent to PUT /api/workouts/{id}/exercises. */
export interface SetIn {
  reps: number;
  weight_kg: number;
  rest_s?: number | null;
  rpe?: number | null;
}

/** A catalog `exercise_key`, or a free-text `name` for exercises the catalog lacks. */
export interface ExerciseIn {
  exercise_key?: string | null;
  name?: string | null;
  sets: SetIn[];
}

export interface CatalogExercise {
  key: string;
  name: string;
  priority: number;
  sets: number;
  rep_min: number;
  rep_max: number;
  rest_s: number;
}

export interface MetricsResponse {
  total: number;
}

export interface HRZone {
  zone: number;
  lower_bpm: number;
  upper_bpm: number;
  seconds_in_zone: number;
}

export interface HRZonesResponse {
  hr_max_bpm: number;
  zones: HRZone[];
}

export interface Macrociclo {
  id: number;
  name: string;
  start_date: string;
  end_date: string;
}

export interface ProgressionPoint {
  microciclo_id: number;
  target_load: number;
  is_deload: boolean;
}

export interface ProgressionResponse {
  macrociclo_id: number;
  points: ProgressionPoint[];
}
