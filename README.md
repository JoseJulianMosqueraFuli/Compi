# Compi

Compi reúne el historial autorizado del iPhone y del reloj Huawei, el registro de fuerza por serie y el tiempo disponible para entrenar. Es una plataforma personal de recomendaciones y un proyecto práctico de MLOps. La primera instalación vive en el iPhone y en el computador.

[Diagrama de arquitectura](docs/arquitectura.md#recorrido-de-los-datos) · [Secuencia de sincronización y reintento](docs/arquitectura.md#sincronización-de-un-lote) · [Estado de la primera importación](docs/operacion-local.md#estado-de-la-primera-sincronización)

## Usar Compi

1. **Conecta el iPhone.** La app nativa lee desde Salud los entrenamientos, el sueño, la frecuencia cardiaca y el peso corporal que elijas compartir. En la misma Wi-Fi, envía los cambios a tu computador por HTTPS. [Instalación local](docs/operacion-local.md) · [App SwiftUI](ios/README.md).
2. **Comprueba qué llegó.** En la portada aparecen la cantidad de muestras y el último lote por categoría. Consulta la serie de pulso o peso por día y origen, o los intervalos de sueño y actividad. En **Entrenamientos importados**, puedes crear un registro editable o vincular la misma actividad a uno existente.
3. **Organiza la semana.** En **Semana** edita tus franjas, el acceso al gimnasio, las excepciones y tus preferencias. Genera la semana para ver qué sesiones de fuerza, caminata y carrera caben y por qué. Las series se registran en el detalle de un entrenamiento.
4. **Evalúa un cambio.** El experimento de duración se puede ejecutar con datos sintéticos o con una sola fuente local. Compara error en minutos y sesiones subestimadas. [Experimento y operación](docs/operacion-local.md#evaluar-la-duración) · [Decisiones de arquitectura y próximos hitos](docs/arquitectura.md).

Las observaciones de Salud conservan su origen. Las sesiones registradas y los planes conservan las ediciones del usuario. La conciliación entre ambos historiales requiere una confirmación en el panel. Si una fuente corrige o elimina la muestra original, el registro que confirmaste conserva sus datos y tus ediciones. El experimento de duración ya consume el historial importado.

## Componentes del proyecto

| Bloque | Tasks | Estado |
|--------|-------|--------|
| 1. Cimientos | 1.1 – 1.4 | ✅ Estructura, config, docker-compose, smoke tests |
| 2. Modelos de datos y migraciones | 2.1 – 2.5 | ✅ 7 entidades SQLModel + Alembic + migración inicial |
| 3. Repositorios | 3.1 – 3.4 | ✅ WorkoutRepo, PlanRepo, TokenRepo + tests |
| 4. Abstracción de proveedor | 4.1 – 4.5 | ✅ WorkoutProvider ABC, MockProvider, select_provider + PBT (Property 9 y 10) |
| 5. Mapeo de entrenamientos | 5.1 – 5.2 | ✅ external_to_workout / workout_to_external + PBT (Property 3) |
| 6. Sincronización y dedup | 7.1 – 7.6 | ✅ partition_new_workouts, needs_refresh, SyncService + APScheduler + PBT (Property 1 y 11) |
| 7. Métricas | 8.1 – 8.6 | ✅ compute_hr_zones, workout_volume, workout_training_load + PBT (Property 4, 5, 6) |
| 8. Periodización y progresión | 9.1 – 9.6 | ✅ PlanService con invariantes temporales, compute_progression, compare_planned_vs_actual + PBT (Property 2, 7, 8) |
| 9. API REST | 11.1 – 11.5 + 13.1 | ✅ routers workouts/metrics/plans, main.py con lifespan, scheduler, CORS, health, PBT (Property 12) |
| 10. Integración Huawei OAuth | 12.1 – 12.3 | Conector directo opcional con OAuth y renovación. Validado con respuestas simuladas; acceso real pendiente. |
| 11. Wiring backend (main.py) | 13.1 | ✅ App FastAPI con lifespan, scheduler, CORS, health, handlers 404/409 |
| 12. Frontend PWA | 15.1 – 15.5 | ✅ Next.js 15 + App Router, PWA instalable, dashboard, vista cardio/fuerza/plan, cliente API tipado |
| 13. Despliegue | 16.1 – 16.2 | Dockerfile del backend y build Next.js para el panel local |
| 14. Registro de fuerza por serie | 18.1 | ✅ `WorkoutExercise` + `ExerciseSet` reemplazan a `StrengthDetail`; `PUT /api/workouts/{id}/exercises` |
| 15. Recomendador semanal (backend) | 18.2 – 18.4 | ✅ Disponibilidad, preferencias, semana recomendada, recálculo, registro y evaluación |
| 16. Migración del recomendador | 18.5 | ✅ `bf03fa6b4c07`: tablas nuevas, datos de `strength_detail` migrados, timestamps a `timestamptz` |
| 17. Tests del recomendador | 18.6 | ✅ Funciones puras (unitarias + PBT) y API de punta a punta |
| 18. Frontend del recomendador | 18.7 – 18.8 | Disponible en `/semana`: franjas, excepciones, preferencias, semana y motivos. Registro por serie en el detalle del entrenamiento. |
| 19. Ingestión personal | Req. 12 | App iOS, receptor HTTPS independiente, procedencia, correcciones y borrados transaccionales |
| 20. Evaluación y operaciones | Req. 13 | Comparación temporal de duraciones por fuente, tracking local opcional en MLflow, OpenTelemetry y CI por componente |

## Estructura del repositorio

```
compi/
├── ios/                           # SwiftUI, HealthKit y estado de sincronización protegido
├── backend/
│   ├── app/
│   │   ├── main.py                 # Inicializacion FastAPI, lifespan, scheduler, CORS
│   │   ├── config.py               # pydantic-settings (DATABASE_URL, HUAWEI_*, SYNC_INTERVAL_MINUTES, CORS)
│   │   ├── db.py                   # engine SQLModel + get_session
│   │   ├── clock.py                # get_now (dependencia para fijar la hora en tests)
│   │   ├── models/                 # SQLModel entities
│   │   │   ├── domain.py           # WorkoutType, SessionKind, SessionStatus, HRZone, ProgressionPoint, Split
│   │   │   ├── workout.py          # Workout, CardioDetail, WorkoutExercise, ExerciseSet + recompute_strength_summary
│   │   │   ├── periodization.py    # Macrociclo, Mesociclo, Microciclo, SesionPlanificada
│   │   │   ├── training.py         # AvailabilityWindow/Exception, TrainingPreferences, WeekPlan, RecommendedSession, PlanChange
│   │   │   └── auth.py             # OAuthToken, UserProfile (singleton id=1)
│   │   ├── repositories/           # Capa de acceso a datos
│   │   │   ├── workout_repo.py
│   │   │   ├── plan_repo.py
│   │   │   └── token_repo.py
│   │   ├── routers/                # API REST
│   │   │   ├── schemas.py          # Esquemas Pydantic
│   │   │   ├── workouts.py         # /api/workouts, /metrics
│   │   │   ├── metrics.py          # /api/metrics/volume, /load
│   │   │   ├── plans.py            # /api/plans/macrocycles, .../progression
│   │   │   ├── availability.py     # /api/availability, /api/preferences, /api/exercises
│   │   │   ├── recommendations.py  # /api/recommendations/week, /sessions, /evaluation
│   │   │   ├── training_schemas.py # Esquemas Pydantic del recomendador
│   │   │   └── auth.py             # /api/auth/huawei/login, /callback
│   │   └── services/               # Lógica de negocio (Req 6, 8, 9)
│   │       ├── week_service.py     # Semana recomendada: generar, recalcular, registrar, evaluar
│   │       ├── recommender/        # Funciones puras del recomendador
│   │       │   ├── availability.py # Ventanas habituales + excepciones -> huecos concretos
│   │       │   ├── scheduler.py    # Ubicar sesiones en huecos y re-ubicarlas (place / replan)
│   │       │   ├── catalog.py      # Ejercicios y plantillas de fuerza
│   │       │   ├── training.py     # Prescripción por historial (doble progresión, deload, carrera +10 %)
│   │       │   ├── duration.py     # Duración estimada y factor aprendido
│   │       │   ├── shorten.py      # Recortar una sesión para que quepa en una ventana
│   │       │   ├── compare.py      # Recomendado vs realizado
│   │       │   └── types.py        # Prescription, Slot y formatos
│   │       ├── dedup.py            # partition_new_workouts (Property 1)
│   │       ├── token_refresh.py    # needs_refresh (Property 11)
│   │       ├── sync_service.py     # SyncService + APScheduler
│   │       ├── metrics_service.py  # HR zones, volume, training load (Properties 4, 5, 6)
│   │       ├── plan_service.py     # PlanService con invariantes temporales (Property 2)
│   │       ├── progression_service.py  # compute_progression con deload 50% (Property 7)
│   │       └── compare_service.py  # compare_planned_vs_actual (Property 8)
│   │   └── providers/              # Abstracción de proveedor (Req 5)
│   │       ├── base.py             # WorkoutProvider ABC + ExternalWorkout/CardioPayload/StrengthSummaryPayload
│   │       ├── mock.py             # MockProvider (datos deterministas)
│   │       ├── huawei.py           # HuaweiProvider real (OAuth + refresh)
│   │       ├── selection.py        # select_provider_kind (Property 9)
│   │       └── mapping.py          # external_to_workout / workout_to_external (Property 3)
│   ├── alembic/                    # Migraciones
│   ├── tests/                      # Pytest + Hypothesis
│   ├── pyproject.toml
 │   ├── alembic.ini
 │   ├── .env.example
 │   └── Dockerfile
 ├── frontend/                       # Next.js 15 PWA
 │   ├── src/
 │   │   ├── app/                    # App Router: /, /workouts/[id], /plan
 │   │   ├── components/             # Nav
 │   │   └── lib/                    # api.ts (cliente tipado) + types.ts
 │   ├── public/                     # manifest, icons, sw.js
 │   ├── .env.example
 │   └── package.json
 ├── docs/                           # Documentación
├── docker-compose.yml              # PostgreSQL 16
├── .gitignore
└── README.md
```

## Requisitos previos

- Python 3.11+ (probado con 3.12)
- Docker y Docker Compose (para PostgreSQL en desarrollo)
- Node.js 20+ (para el frontend)

## Backend - Desarrollo local

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Levantar PostgreSQL
docker compose up -d db

# Aplicar migraciones
alembic upgrade head

# Arrancar API
uvicorn app.main:app --host 127.0.0.1 --no-access-log --reload
```

Endpoints principales:

- `GET /health` — proceso vivo
- `GET /ready` — comprueba la conexión a la base
- `GET /api/healthkit/coverage` — cobertura, procedencia y última recepción
- `POST /api/healthkit/duration-evaluation` — evaluación retrospectiva por fuente
- `GET /api/workouts` — lista workouts
- `GET /api/workouts/{id}` — detalle (404 si no existe)
- `PUT /api/workouts/{id}/exercises` — registro de fuerza serie a serie; reemplaza el registro anterior (Req 3.5)
- `GET /api/workouts/{id}/metrics` — zonas FC
- `GET /api/metrics/volume` — volumen agregado
- `GET /api/metrics/load` — carga de entrenamiento agregada
- `GET /api/plans/macrocycles` — lista macrociclos
- `POST /api/plans/macrocycles|mesocycles|microcycles|sessions` — crear nodos
- `GET /api/plans/{id}/progression` — carga objetivo por microciclo
- `GET /api/auth/huawei/login` — inicia el flujo OAuth (redirige a Huawei)
- `GET /api/auth/huawei/callback` — intercambia el code por tokens y persiste el refresh token

Recomendador semanal:

- `GET /api/availability` — semana habitual y excepciones
- `PUT /api/availability/windows` — reemplaza la semana habitual (400 si se solapan ventanas del mismo día)
- `POST /api/availability/exceptions` · `DELETE /api/availability/exceptions/{id}` — excepción de una fecha (sin horas bloquea el día)
- `GET|PUT /api/preferences` — sesiones por semana, duraciones, zona horaria, ejercicios excluidos
- `GET /api/exercises` — catálogo de ejercicios
- `GET /api/recommendations/week?day=` — semana guardada (404 hasta generarla)
- `POST /api/recommendations/week` — genera la semana; con `regenerate` rehace solo lo pendiente
- `POST /api/recommendations/week/{id}/recalculate` — re-ubica lo pendiente en las ventanas que quedan
- `GET /api/recommendations/sessions/{id}` — sesión con su comparación recomendado vs realizado
- `POST /api/recommendations/sessions/{id}/log|skip|reopen` — registrar, saltar o reabrir una sesión
- `GET /api/recommendations/evaluation` — duración estimada vs real, adherencia y progresión

Editar la disponibilidad recalcula las sesiones pendientes de las semanas abiertas y devuelve en `changes` qué cambió y por qué.

Variables de entorno (ver `backend/.env.example`):

- `DATABASE_URL` — URL de conexión a PostgreSQL
- `HEALTHKIT_SYNC_TOKEN` — secreto local compartido con el iPhone para el receptor HTTPS
- `LEGACY_SYNC_MODE` — `off` por defecto. `demo` es para una base sintética independiente. `huawei` requiere OAuth y credenciales `HUAWEI_*`
- `SYNC_INTERVAL_MINUTES` — periodicidad de la sincronización (por defecto 60)
- `CORS_ALLOWED_ORIGINS` — lista JSON de orígenes permitidos

## Tests

```bash
cd backend
pytest                  # ejecuta todos los tests
pytest -m ""            # sin filtros de marcadores
pytest --tb=short       # trazas cortas
```

Los tests se organizan en:

- `test_setup.py` — smoke tests de configuración y estructura (Req 1.1, 2.1, 2.3, 2.4)
- `test_models.py` — entidades SQLModel, jerarquía, unicidad
- `test_repositories.py` — repositorios con SQLite en memoria
- `test_provider_properties.py` — PBT (Hypothesis) para Properties 9 y 10
- `test_mapping_properties.py` — PBT (Hypothesis) para Property 3 (round-trip)
- `test_sync_properties.py` — PBT para Properties 1 (dedup) y 11 (refresh)
- `test_sync_integration.py` — integración SyncService + MockProvider (idempotencia, dedup, persistencia)
- `test_metrics_properties.py` — PBT para Properties 4 (zonas FC), 5 (volumen) y 6 (carga)
- `test_periodization_properties.py` — PBT para Properties 2 (jerarquía), 7 (progresión) y 8 (comparación)
- `test_api.py` — routers con TestClient; PBT Property 12 (404) + smoke tests de plans y metrics
- `test_recommender.py` — funciones puras del recomendador: duración, recorte, disponibilidad, scheduler, prescripción y comparación (unitarias + PBT)
- `test_recommendations_api.py` — disponibilidad, preferencias y semana recomendada de punta a punta (reloj fijado con `get_now`)

Cobertura de las 12 propiedades de corrección del design:

| Property | Validates | Test |
|----------|-----------|------|
| 1  | Req 6.2, 6.3 (deduplicación) | `test_sync_properties.py` |
| 2  | Req 4.1, 4.3 (jerarquía periodización) | `test_periodization_properties.py` |
| 3  | Req 3.1, 3.2, 3.3 (round-trip) | `test_mapping_properties.py` |
| 4  | Req 8.1 (zonas FC bien formadas) | `test_metrics_properties.py` |
| 5  | Req 8.2 (volumen no negativo y aditivo) | `test_metrics_properties.py` |
| 6  | Req 8.3 (carga no negativa y monótona) | `test_metrics_properties.py` |
| 7  | Req 9.1, 9.2 (progresión con deload) | `test_periodization_properties.py` |
| 8  | Req 9.3 (planificado vs real) | `test_periodization_properties.py` |
| 9  | Req 1.4, 11.1 (selección proveedor) | `test_provider_properties.py` |
| 10 | Req 5.2 (MockProvider bien formado) | `test_provider_properties.py` |
| 11 | Req 6.4 (decisión de refresco) | `test_sync_properties.py` |
| 12 | Req 7.4 (recurso inexistente -> 404) | `test_api.py` |

## Lint y formato

```bash
cd backend
ruff check app/ tests/      # lint
ruff check app/ tests/ --fix
```

## Frontend - Desarrollo local

El frontend usa **pnpm** como gestor de dependencias (lockfile versionado `pnpm-lock.yaml`, scripts de postinstall deshabilitados por defecto).

```bash
cd frontend
corepack enable              # si pnpm no está instalado
pnpm install
cp .env.example .env.local   # ajustar NEXT_PUBLIC_API_URL
pnpm dev --hostname 127.0.0.1 # http://localhost:3000
```

Scripts disponibles (`pnpm <script>`): `dev`, `build`, `start`, `lint`, `typecheck`.

**Política de seguridad de pnpm:**
- `engine-strict=true` en `.npmrc`: rechaza instalaciones si no coincide con la `packageManager` declarada en `package.json`.
- `ignore-scripts=true` por defecto: los `postinstall` de dependencias no se ejecutan.
- Lista explícita de builds nativos permitidos en `package.json#pnpm.onlyBuiltDependencies` (solo `sharp` y `unrs-resolver`, requeridos por Next.js). Para añadir otro, edita la lista a propósito y ejecuta `pnpm approve-builds <pkg>`.

Vistas implementadas:

- `/` — Panel con cobertura de Salud y comparación de duración por fuente, además de entrenamientos registrados
- `/semana` — Horario habitual editable, excepciones, zona horaria y recomendaciones con sus motivos
- `/workouts/[id]` — Detalle cardio (zonas FC, pace) o fuerza (resumen + registro serie a serie: ejercicios del catálogo o libres, editable)
- `/plan` — Lista de macrociclos y progresión objetivo por microciclo

PWA: `manifest.json` + iconos SVG + service worker en `public/sw.js` (caché limitada a la portada pública y assets estáticos; las respuestas de salud se consultan en el backend local).

## Documentación

- `.kiro/specs/compi-training-platform/requirements.md` — requisitos del MVP
- `.kiro/specs/compi-training-platform/design.md` — diseño, fórmulas y propiedades de corrección
- `.kiro/specs/compi-training-platform/tasks.md` — plan de implementación (MVP + tarea 18, recomendador semanal)
