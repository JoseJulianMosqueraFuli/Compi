# Compi - Training Platform

Plataforma personal de entrenamiento (MVP) que sincroniza entrenamientos desde Huawei Health Kit, los persiste, calcula métricas y permite planificar mediante periodización.

## Estado del desarrollo

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
| 10. Integración Huawei OAuth | 12.1 – 12.3 | ✅ HuaweiProvider real con OAuth, refresh y mapeo de respuesta; router auth con /login y /callback |
| 11. Wiring backend (main.py) | 13.1 | ✅ App FastAPI con lifespan, scheduler, CORS, health, handlers 404/409 |
| 12. Frontend PWA | 15.1 – 15.5 | ✅ Next.js 15 + App Router, PWA instalable, dashboard, vista cardio/fuerza/plan, cliente API tipado |
| 13. Despliegue | 16.1 – 16.2 | ✅ Dockerfile del backend, build estático del frontend (Next.js) |

Tests backend: **73 / 73 pasan** · Lint backend: limpio · Frontend: typecheck + lint + build OK.

## Estructura del repositorio

```
compi/
├── backend/
│   ├── app/
│   │   ├── main.py                 # Inicializacion FastAPI, lifespan, scheduler, CORS
│   │   ├── config.py               # pydantic-settings (DATABASE_URL, HUAWEI_*, SYNC_INTERVAL_MINUTES, CORS)
│   │   ├── db.py                   # engine SQLModel + get_session
│   │   ├── models/                 # SQLModel entities
│   │   │   ├── domain.py           # WorkoutType, HRZone, ProgressionPoint, PlannedVsActual, Split
│   │   │   ├── workout.py          # Workout, CardioDetail, StrengthDetail + recompute_strength_summary
│   │   │   ├── periodization.py    # Macrociclo, Mesociclo, Microciclo, SesionPlanificada
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
│   │   │   └── auth.py             # /api/auth/huawei/login, /callback
│   │   └── services/               # Lógica de negocio (Req 6, 8, 9)
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
uvicorn app.main:app --reload
```

Endpoints principales:

- `GET /health` — health check
- `GET /api/workouts` — lista workouts
- `GET /api/workouts/{id}` — detalle (404 si no existe)
- `POST /api/workouts/{id}/strength-detail` — registro manual (Req 3.5)
- `GET /api/workouts/{id}/metrics` — zonas FC
- `GET /api/metrics/volume` — volumen agregado
- `GET /api/metrics/load` — carga de entrenamiento agregada
- `GET /api/plans/macrocycles` — lista macrociclos
- `POST /api/plans/macrocycles|mesocycles|microcycles|sessions` — crear nodos
- `GET /api/plans/{id}/progression` — carga objetivo por microciclo
- `GET /api/auth/huawei/login` — inicia el flujo OAuth (redirige a Huawei)
- `GET /api/auth/huawei/callback` — intercambia el code por tokens y persiste el refresh token

Variables de entorno (ver `backend/.env.example`):

- `DATABASE_URL` — URL de conexión a PostgreSQL
- `HUAWEI_CLIENT_ID`, `HUAWEI_CLIENT_SECRET`, `HUAWEI_REDIRECT_URI` — opcionales; sin ellas se usa `MockProvider` (Req 1.4)
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
pnpm dev                     # http://localhost:3000
```

Scripts disponibles (`pnpm <script>`): `dev`, `build`, `start`, `lint`, `typecheck`.

**Política de seguridad de pnpm:**
- `engine-strict=true` en `.npmrc`: rechaza instalaciones si no coincide con la `packageManager` declarada en `package.json`.
- `ignore-scripts=true` por defecto: los `postinstall` de dependencias no se ejecutan.
- Lista explícita de builds nativos permitidos en `package.json#pnpm.onlyBuiltDependencies` (solo `sharp` y `unrs-resolver`, requeridos por Next.js). Para añadir otro, edita la lista a propósito y ejecuta `pnpm approve-builds <pkg>`.

Vistas implementadas:

- `/` — Dashboard con métricas agregadas y últimos workouts
- `/workouts/[id]` — Detalle cardio (zonas FC, pace) o fuerza (volumen + formulario manual de `StrengthDetail`)
- `/plan` — Lista de macrociclos y progresión objetivo por microciclo

PWA: `manifest.json` + iconos SVG + service worker en `public/sw.js` (cache-first para estáticos, network-first para navegaciones, registro client-side en `layout.tsx`).

## Documentación

- `.kiro/specs/compi-training-platform/requirements.md` — requisitos del MVP
- `.kiro/specs/compi-training-platform/design.md` — diseño, fórmulas y propiedades de corrección
- `.kiro/specs/compi-training-platform/tasks.md` — plan de implementación completo
