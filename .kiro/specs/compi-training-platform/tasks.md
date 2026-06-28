# Implementation Plan: Compi Training Platform

## Overview

Plan de implementación incremental para el MVP de Compi. El backend se construye en **Python** con FastAPI, SQLModel + Alembic y APScheduler; las pruebas basadas en propiedades usan **Hypothesis**. Cada tarea se apoya en las anteriores: primero los cimientos y el modelo de datos, luego la lógica de negocio pura (deduplicación, métricas, periodización, progresión) que concentra las propiedades de corrección, después la API, la integración con Huawei, el cableado de la aplicación y finalmente la PWA y el despliegue. Las sub-tareas de pruebas están marcadas con `*` y son opcionales.

## Tasks

- [ ] 1. Cimientos del proyecto y entorno de desarrollo
  - [ ] 1.1 Crear la estructura del repositorio y la configuración del backend
    - Crear directorios `backend/app/{models,repositories,services,providers,routers}`, `frontend/` y `docs/`
    - Crear `backend/pyproject.toml` con dependencias: FastAPI, SQLModel, Alembic, pydantic-settings, APScheduler, Hypothesis, pytest
    - Crear `README.md` con instrucciones de instalación/ejecución y `.gitignore`
    - _Requirements: 2.1, 2.4_

  - [ ] 1.2 Configurar carga de variables de entorno y acceso a base de datos
    - Implementar `app/config.py` con `pydantic-settings` leyendo `DATABASE_URL`, `HUAWEI_CLIENT_ID`, `HUAWEI_CLIENT_SECRET`, `HUAWEI_REDIRECT_URI`, `SYNC_INTERVAL_MINUTES`
    - Implementar `app/db.py` con el engine SQLModel y la gestión de sesiones
    - _Requirements: 1.1, 2.3_

  - [ ] 1.3 Configurar docker-compose con PostgreSQL para desarrollo local
    - Crear `docker-compose.yml` que levante una instancia de PostgreSQL para desarrollo
    - _Requirements: 2.2_

  - [ ]\* 1.4 Escribir prueba smoke de configuración y estructura
    - Verificar carga de variables de entorno requeridas y existencia de directorios/README/.gitignore
    - _Requirements: 1.1, 2.1, 2.3, 2.4_

- [ ] 2. Modelos de datos y migraciones
  - [ ] 2.1 Definir tipos de valor de dominio y enums
    - Implementar `WorkoutType`, `HRZone`, `ProgressionPoint`, `PlannedVsActual` en `app/models/`
    - _Requirements: 3.1_

  - [ ] 2.2 Implementar entidades Workout, CardioDetail y StrengthDetail
    - Crear `app/models/workout.py` con `Workout` (incl. `external_id` único e indexado, resumen de fuerza embebido), `CardioDetail` (GPS/pace/splits) y `StrengthDetail`
    - _Requirements: 3.1, 3.2, 3.3, 3.4_

  - [ ] 2.3 Implementar entidades de periodización
    - Crear `app/models/periodization.py` con `Macrociclo`, `Mesociclo`, `Microciclo` y `SesionPlanificada`, incluyendo claves foráneas jerárquicas y el FK opcional a `Workout`
    - _Requirements: 4.1, 4.2_

  - [ ] 2.4 Implementar entidad OAuthToken
    - Crear `app/models/auth.py` con `OAuthToken` (`provider`, `refresh_token`, `access_token`, `expires_at`)
    - _Requirements: 1.3, 6.4_

  - [ ] 2.5 Configurar Alembic y generar la migración inicial
    - Inicializar `backend/alembic/`, configurar el target metadata de SQLModel y generar la migración del esquema base
    - _Requirements: 2.2, 3.1, 4.1_

- [ ] 3. Capa de repositorios
  - [ ] 3.1 Implementar WorkoutRepository
    - Crear `app/repositories/workout_repo.py` con `exists(external_id)`, `insert`, `get` (señaliza inexistente), `list` con filtros por tipo/fecha
    - _Requirements: 6.2, 6.3, 7.1, 7.4_

  - [ ] 3.2 Implementar PlanRepository
    - Crear `app/repositories/plan_repo.py` para persistir y consultar la jerarquía de periodización y asociar sesiones a workouts
    - _Requirements: 4.1, 4.2, 4.3, 7.3_

  - [ ] 3.3 Implementar TokenRepository
    - Crear `app/repositories/token_repo.py` para persistir y recuperar el `Token_De_Refresco`
    - _Requirements: 1.3, 6.4_

  - [ ]\* 3.4 Escribir pruebas unitarias de repositorios
    - Probar persistencia y recuperación de StrengthDetail asociado al Workout, asociación de SesionPlanificada con un Workout real, y persistencia del Token_De_Refresco
    - _Requirements: 3.5, 4.2, 1.3_

- [ ] 4. Abstracción de proveedor y selección
  - [ ] 4.1 Definir la interfaz WorkoutProvider y los esquemas ExternalWorkout
    - Crear `app/providers/base.py` con la ABC `WorkoutProvider` (`authenticate`, `is_authenticated`, `fetch_workouts`) y los modelos `ExternalWorkout`, `CardioPayload`, `StrengthSummaryPayload`
    - _Requirements: 5.1_

  - [ ] 4.2 Implementar MockProvider
    - Crear `app/providers/mock.py` que devuelva entrenamientos cardio (GPS/pace/splits) y fuerza (resumen) con `external_id` deterministas, sin requerir credenciales
    - _Requirements: 5.2, 5.4_

  - [ ]\* 4.3 Escribir prueba de propiedad para los datos del MockProvider
    - **Property 10: Datos del MockProvider bien formados**
    - **Validates: Requirements 5.2**

  - [ ] 4.4 Implementar la lógica de selección de proveedor activo
    - Crear función pura `select_provider(config, has_token)` que aplique la regla determinista (sin credenciales → MockProvider; con credenciales y token válido → HuaweiProvider)
    - _Requirements: 1.4, 11.1_

  - [ ]\* 4.5 Escribir prueba de propiedad para la selección de proveedor
    - **Property 9: Selección de proveedor según configuración**
    - **Validates: Requirements 1.4, 11.1**

- [ ] 5. Mapeo de entrenamientos
  - [ ] 5.1 Implementar el mapeo ExternalWorkout ↔ Workout
    - Crear funciones puras de mapeo que conviertan un `ExternalWorkout` (cardio/fuerza) a las entidades persistibles y reconstruyan el `ExternalWorkout`
    - _Requirements: 3.1, 3.2, 3.3_

  - [ ]\* 5.2 Escribir prueba de propiedad para el round-trip de mapeo
    - **Property 3: Round-trip de mapeo de entrenamientos**
    - **Validates: Requirements 3.1, 3.2, 3.3**

- [ ] 6. Checkpoint - Asegurar que las pruebas pasan
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 7. Sincronización y deduplicación
  - [ ] 7.1 Implementar la función pura de partición/deduplicación
    - Crear `partition_new_workouts(existing_ids, fetched)` que separe entrenamientos en "nuevos" y "omitidos" según `external_id`
    - _Requirements: 6.2, 6.3_

  - [ ]\* 7.2 Escribir prueba de propiedad para la deduplicación
    - **Property 1: Deduplicación por partición de external_id**
    - **Validates: Requirements 6.2, 6.3**

  - [ ] 7.3 Implementar la decisión pura de refresco de token
    - Crear `needs_refresh(expires_at, now, margin)` que devuelva verdadero si y solo si el token está expirado o dentro del margen
    - _Requirements: 6.4_

  - [ ]\* 7.4 Escribir prueba de propiedad para la decisión de refresco de token
    - **Property 11: Decisión de refresco de token**
    - **Validates: Requirements 6.4**

  - [ ] 7.5 Implementar SyncService e integrarlo con el scheduler
    - Crear `app/services/sync_service.py` que use el proveedor activo, refresque el token si procede, aplique la deduplicación e inserte transaccionalmente cada workout nuevo
    - _Requirements: 6.1, 6.2, 6.3, 6.4_

  - [ ]\* 7.6 Escribir prueba de integración de la sincronización con MockProvider
    - Ejecutar el ciclo de sincronización sin credenciales y verificar inserción de nuevos y omisión de duplicados
    - _Requirements: 5.4, 6.1_

- [ ] 8. Servicio de métricas
  - [ ] 8.1 Implementar el cálculo de zonas de frecuencia cardiaca
    - Crear `app/services/metrics_service.py` con el cálculo de `Zonas_De_FC` (ordenadas, contiguas, no solapadas) a partir de la FC máxima y de reposo opcional
    - _Requirements: 8.1_

  - [ ]\* 8.2 Escribir prueba de propiedad para las zonas de FC
    - **Property 4: Zonas de frecuencia cardiaca bien formadas y exhaustivas**
    - **Validates: Requirements 8.1**

  - [ ] 8.3 Implementar el cálculo del volumen de entrenamiento
    - Añadir el cálculo de volumen agregado (no negativo y aditivo) sobre conjuntos de entrenamientos
    - _Requirements: 8.2_

  - [ ]\* 8.4 Escribir prueba de propiedad para el volumen de entrenamiento
    - **Property 5: Volumen de entrenamiento no negativo y aditivo**
    - **Validates: Requirements 8.2**

  - [ ] 8.5 Implementar el cálculo de la carga de entrenamiento
    - Añadir el cálculo de `Carga_De_Entrenamiento` (no negativa y monótona no decreciente)
    - _Requirements: 8.3_

  - [ ]\* 8.6 Escribir prueba de propiedad para la carga de entrenamiento
    - **Property 6: Carga de entrenamiento no negativa y monótona**
    - **Validates: Requirements 8.3**

- [ ] 9. Servicios de planificación y progresión
  - [ ] 9.1 Implementar PlanService para la jerarquía de periodización
    - Crear `app/services/plan_service.py` para crear y persistir macrociclos/mesociclos/microciclos/sesiones manteniendo la integridad jerárquica y vinculando cada sesión a su microciclo
    - _Requirements: 4.1, 4.2, 4.3_

  - [ ]\* 9.2 Escribir prueba de propiedad para la integridad de la jerarquía
    - **Property 2: Integridad de la jerarquía de periodización**
    - **Validates: Requirements 4.1, 4.3**

  - [ ] 9.3 Implementar la secuencia de progresión con incremento y deload
    - Crear `app/services/progression_service.py` que calcule la carga objetivo por microciclo aplicando el incremento porcentual y reduciendo en los microciclos de descarga
    - _Requirements: 9.1, 9.2_

  - [ ]\* 9.4 Escribir prueba de propiedad para la secuencia de progresión
    - **Property 7: Secuencia de progresión con incremento y deload**
    - **Validates: Requirements 9.1, 9.2**

  - [ ] 9.5 Implementar la comparación planificado vs. real
    - Añadir el cálculo de `PlannedVsActual` (delta = real − planificado, signo y cero correctos)
    - _Requirements: 9.3_

  - [ ]\* 9.6 Escribir prueba de propiedad para la comparación planificado vs. real
    - **Property 8: Comparación planificado vs. real**
    - **Validates: Requirements 9.3**

- [ ] 10. Checkpoint - Asegurar que las pruebas pasan
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 11. API REST
  - [ ] 11.1 Implementar el router de workouts y el manejador global de 404
    - Crear `app/routers/workouts.py` con `GET /api/workouts`, `GET /api/workouts/{id}`, `POST /api/workouts/{id}/strength-detail`, `GET /api/workouts/{id}/metrics`; añadir el handler global que traduce `NotFoundError` a `404`
    - _Requirements: 7.1, 7.4, 3.5, 8.1_

  - [ ]\* 11.2 Escribir prueba de propiedad para recurso inexistente
    - **Property 12: Recurso inexistente devuelve error**
    - **Validates: Requirements 7.4**

  - [ ] 11.3 Implementar el router de métricas
    - Crear `app/routers/metrics.py` con `GET /api/metrics/volume` y `GET /api/metrics/load`
    - _Requirements: 7.2, 8.2, 8.3_

  - [ ] 11.4 Implementar el router de planes
    - Crear `app/routers/plans.py` con endpoints de creación de macrociclos/mesociclos/microciclos/sesiones, listado y `GET /api/plans/{macro_id}/progression`
    - _Requirements: 7.3, 4.3, 9.1, 9.3_

  - [ ]\* 11.5 Escribir pruebas unitarias de los routers de métricas y planes
    - Probar respuestas 200, formato JSON y asociación de sesión planificada con workout real
    - _Requirements: 7.2, 7.3, 4.2_

- [ ] 12. Integración con Huawei Health Kit
  - [ ] 12.1 Implementar el router de autenticación OAuth
    - Crear `app/routers/auth.py` con `GET /api/auth/huawei/login` y `GET /api/auth/huawei/callback` que persiste el Token_De_Refresco; error 400 si el callback falla
    - _Requirements: 1.2, 1.3_

  - [ ] 12.2 Implementar HuaweiProvider
    - Crear `app/providers/huawei.py` que implemente `WorkoutProvider`, renueve el token expirado antes de descargar y mapee respuestas de Huawei a `ExternalWorkout`
    - _Requirements: 5.3, 6.4, 11.1_

  - [ ]\* 12.3 Escribir pruebas de integración de OAuth y descarga Huawei
    - Probar el flujo OAuth contra endpoints simulados y `HuaweiProvider.fetch_workouts` mapeando respuestas simuladas
    - _Requirements: 1.2, 5.3_

- [ ] 13. Cableado de la aplicación backend
  - [ ] 13.1 Inicializar la app FastAPI y conectar todos los componentes
    - Implementar `app/main.py`: registrar routers, manejadores de error globales, seleccionar el proveedor activo al arranque y arrancar el scheduler de sincronización en el ciclo de vida
    - _Requirements: 1.4, 6.1, 7.4, 11.1_

- [ ] 14. Checkpoint - Asegurar que las pruebas pasan
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 15. Frontend PWA
  - [ ] 15.1 Inicializar Next.js como PWA con cliente API tipado
    - Configurar el proyecto Next.js con manifest, service worker (caché del shell) y un cliente HTTP tipado hacia la API REST
    - _Requirements: 10.1_

  - [ ] 15.2 Implementar el Dashboard
    - Crear la vista `/` con resumen de entrenamientos recientes y métricas clave
    - _Requirements: 10.2_

  - [ ] 15.3 Implementar la vista Cardio
    - Crear la vista de detalle cardio con mapa (GPS), zonas de FC y pace
    - _Requirements: 10.3_

  - [ ] 15.4 Implementar la vista Fuerza con registro manual
    - Crear la vista de detalle fuerza con volumen, progreso y formulario de registro manual de StrengthDetail
    - _Requirements: 10.4, 3.5_

  - [ ] 15.5 Implementar la vista Plan
    - Crear la vista `/plan` con los niveles macrociclo/mesociclo/microciclo y su progreso
    - _Requirements: 10.5_

  - [ ]\* 15.6 Escribir pruebas de componente/snapshot del frontend
    - Cubrir dashboard, vista cardio, vista fuerza y vista plan
    - _Requirements: 10.2, 10.3, 10.4, 10.5_

- [ ] 16. Configuración de despliegue
  - [ ] 16.1 Crear el Dockerfile del backend y la configuración de despliegue en la nube
    - Crear `backend/Dockerfile` y la configuración para desplegar backend + PostgreSQL en un servicio en la nube
    - _Requirements: 11.2_

  - [ ] 16.2 Crear la configuración de despliegue del frontend
    - Configurar el despliegue de la PWA en un servicio de hospedaje web
    - _Requirements: 11.3_

- [ ] 17. Checkpoint final - Asegurar que las pruebas pasan
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Las tareas marcadas con `*` son opcionales y pueden omitirse para un MVP más rápido.
- Cada tarea referencia requisitos específicos para trazabilidad.
- Los checkpoints aseguran validación incremental.
- Las pruebas de propiedad (Hypothesis, mínimo 100 iteraciones) validan las 12 propiedades de corrección universales; cada propiedad tiene su propia sub-tarea.
- Las pruebas unitarias y de integración validan ejemplos concretos y comportamientos que dependen de infraestructura o servicios externos.
- No se aplica PBT al renderizado de la UI; el frontend se cubre con pruebas de componente/snapshot.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["1.2", "1.3", "1.4"] },
    { "id": 2, "tasks": ["2.1"] },
    { "id": 3, "tasks": ["2.2", "2.3", "2.4"] },
    { "id": 4, "tasks": ["2.5", "4.1"] },
    { "id": 5, "tasks": ["3.1", "3.2", "3.3", "4.2", "4.4", "5.1"] },
    {
      "id": 6,
      "tasks": [
        "3.4",
        "4.3",
        "4.5",
        "5.2",
        "7.1",
        "7.3",
        "8.1",
        "8.3",
        "8.5",
        "9.1",
        "9.3",
        "9.5"
      ]
    },
    {
      "id": 7,
      "tasks": [
        "7.2",
        "7.4",
        "7.5",
        "8.2",
        "8.4",
        "8.6",
        "9.2",
        "9.4",
        "9.6",
        "12.2"
      ]
    },
    { "id": 8, "tasks": ["7.6", "11.1", "11.3", "11.4", "12.1"] },
    { "id": 9, "tasks": ["11.2", "11.5", "12.3", "13.1"] },
    { "id": 10, "tasks": ["15.1", "16.1", "16.2"] },
    { "id": 11, "tasks": ["15.2", "15.3", "15.4", "15.5"] },
    { "id": 12, "tasks": ["15.6"] }
  ]
}
```
