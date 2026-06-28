# Compi - Training Platform

Plataforma personal de entrenamiento (MVP) que sincroniza entrenamientos desde Huawei Health Kit, los persiste, calcula métricas y permite planificar mediante periodización.

## Estado del desarrollo

| Bloque | Tasks | Estado |
|--------|-------|--------|
| 1. Cimientos | 1.1 – 1.4 | ✅ Estructura, config, docker-compose, smoke tests |
| 2. Modelos de datos y migraciones | 2.1 – 2.5 | ✅ 7 entidades SQLModel + Alembic + migración inicial |
| 3. Repositorios | 3.1 – 3.4 | ✅ WorkoutRepo, PlanRepo, TokenRepo + tests |
| 4. Abstracción de proveedor | 4.1 – 4.5 | ✅ WorkoutProvider ABC, MockProvider, select_provider + PBT (Property 9 y 10) |
| 5. Mapeo de entrenamientos | 5.1 – 5.2 | ⏳ Pendiente |
| 6. Sincronización y dedup | 7.1 – 7.6 | ⏳ Pendiente |
| 7. Métricas | 8.1 – 8.6 | ⏳ Pendiente |
| 8. Periodización y progresión | 9.1 – 9.6 | ⏳ Pendiente |
| 9. API REST | 11.1 – 11.5 | ⏳ Pendiente |
| 10. Integración Huawei OAuth | 12.1 – 12.3 | ⏳ Pendiente |
| 11. Wiring backend (main.py) | 13.1 | ⏳ Pendiente |
| 12. Frontend PWA | 15.1 – 15.6 | ⏳ Pendiente |
| 13. Despliegue | 16.1 – 16.2 | ⏳ Pendiente |

Tests: **28 / 28 pasan** · Lint: limpio.

## Estructura del repositorio

```
compi/
├── backend/
│   ├── app/
│   │   ├── main.py                 # Inicializacion FastAPI (pendiente)
│   │   ├── config.py               # pydantic-settings (DATABASE_URL, HUAWEI_*, SYNC_INTERVAL_MINUTES)
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
│   │   └── providers/              # Abstracción de proveedor (Req 5)
│   │       ├── base.py             # WorkoutProvider ABC + ExternalWorkout/CardioPayload/StrengthSummaryPayload
│   │       ├── mock.py             # MockProvider (datos deterministas)
│   │       ├── huawei.py           # Stub (se completa en task 12.2)
│   │       └── selection.py        # select_provider_kind (Property 9)
│   ├── alembic/                    # Migraciones
│   ├── tests/                      # Pytest + Hypothesis
│   ├── pyproject.toml
│   ├── alembic.ini
│   ├── .env.example
│   └── Dockerfile                  # Pendiente
├── frontend/                       # Next.js PWA (pendiente)
├── docs/                           # Documentación
├── docker-compose.yml              # PostgreSQL 16
├── .gitignore
└── README.md
```

## Requisitos previos

- Python 3.11+ (probado con 3.12)
- Docker y Docker Compose (para PostgreSQL en desarrollo)
- Node.js 20+ (para el frontend, cuando se implemente)

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

# Arrancar API (pendiente: app.main)
# uvicorn app.main:app --reload
```

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

Cobertura de las 12 propiedades de corrección del design:

| Property | Validates | Test |
|----------|-----------|------|
| 9  | Req 1.4, 11.1 (selección proveedor) | `test_provider_properties.py` |
| 10 | Req 5.2 (MockProvider bien formado) | `test_provider_properties.py` |
| Resto (1–8, 11, 12) | — | Pendientes (bloques 5–11) |

## Lint y formato

```bash
cd backend
ruff check app/ tests/      # lint
ruff check app/ tests/ --fix
```

## Frontend - Desarrollo local

```bash
cd frontend
npm install
npm run dev
```

(Placeholder — el frontend se implementa en los bloques 12 y siguientes.)

## Documentación

- `.kiro/specs/compi-training-platform/requirements.md` — requisitos del MVP
- `.kiro/specs/compi-training-platform/design.md` — diseño, fórmulas y propiedades de corrección
- `.kiro/specs/compi-training-platform/tasks.md` — plan de implementación completo
