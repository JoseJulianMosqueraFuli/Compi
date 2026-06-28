# Compi - Training Platform

Plataforma personal de entrenamiento (MVP) que sincroniza entrenamientos desde Huawei Health Kit, los persiste, calcula métricas y permite planificar mediante periodización.

## Estructura del repositorio

```
compi/
├── backend/          # FastAPI + SQLModel + Alembic
├── frontend/         # Next.js PWA
├── docs/             # Documentación
├── docker-compose.yml
├── .gitignore
└── README.md
```

## Requisitos previos

- Python 3.11+
- Docker y Docker Compose (para PostgreSQL en desarrollo)
- Node.js 20+ (para el frontend)

## Backend - Desarrollo local

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Levantar PostgreSQL
docker compose up -d db

# Aplicar migraciones
alembic upgrade head

# Arrancar API
uvicorn app.main:app --reload
```

Variables de entorno (ver `backend/.env.example`):

- `DATABASE_URL` — URL de conexión a PostgreSQL
- `HUAWEI_CLIENT_ID`, `HUAWEI_CLIENT_SECRET`, `HUAWEI_REDIRECT_URI` — opcionales; sin ellas se usa `MockProvider`
- `SYNC_INTERVAL_MINUTES` — periodicidad de la sincronización (por defecto 60)

## Frontend - Desarrollo local

```bash
cd frontend
npm install
npm run dev
```

## Tests

```bash
cd backend
pytest
```

Los tests de propiedad (Hypothesis) validan las 12 propiedades de corrección definidas en `.kiro/specs/compi-training-platform/design.md`.

## Documentación

- `.kiro/specs/compi-training-platform/requirements.md` — requisitos del MVP
- `.kiro/specs/compi-training-platform/design.md` — diseño y propiedades de corrección
- `.kiro/specs/compi-training-platform/tasks.md` — plan de implementación
