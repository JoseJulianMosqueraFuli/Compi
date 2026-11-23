# Requirements Document

## Introduction

Compi es el complemento personal de Salud de Apple para registrar fuerza en gimnasio, caminatas y carreras al aire libre y recomendar sesiones que quepan en un horario semanal editable. El reloj Huawei y el iPhone pueden aportar muestras. La aplicación nativa importa las categorías autorizadas desde HealthKit y conserva la app de origen. El panel, el historial y el motor de reglas se ejecutan en el computador.

La implementación inicial usa SwiftUI, FastAPI, SQLModel/Alembic, PostgreSQL y una PWA Next.js. La integración directa de Huawei permanece como un conector opcional. La [arquitectura y evolución](../../../docs/arquitectura.md) recoge las decisiones, los ensayos de MLOps y los criterios para pasar a otros entornos.

## Glossary

- **Compi**: Sistema completo (backend, frontend, base de datos y servicios de sincronización) que da soporte a la plataforma de entrenamiento.
- **Backend**: Servicio FastAPI que expone la API REST y ejecuta la lógica de negocio.
- **Frontend**: Aplicación Next.js entregada como PWA (Progressive Web App).
- **Base_De_Datos**: Instancia PostgreSQL que persiste los datos del sistema.
- **Workout**: Entrenamiento real ejecutado por el usuario; incluye tipo (cardio o fuerza), duración, frecuencia cardiaca, calorías y datos enriquecidos según el tipo.
- **Registro de fuerza**: WorkoutExercise identifica el ejercicio y ExerciseSet conserva peso, repeticiones, descanso y esfuerzo de cada serie.
- **Macrociclo**: Periodo de planificación de mayor nivel que agrupa mesociclos.
- **Mesociclo**: Periodo de planificación intermedio que agrupa microciclos.
- **Microciclo**: Periodo de planificación corto (típicamente semanal) que agrupa sesiones planificadas.
- **Sesion_Planificada**: Entrenamiento previsto dentro de un microciclo, asociable a un Workout real.
- **WorkoutProvider**: Interfaz común que define las operaciones de autenticación y descarga de entrenamientos desde una fuente externa.
- **MockProvider**: Implementación de `WorkoutProvider` que devuelve datos de prueba realistas para desarrollo.
- **HuaweiProvider**: Implementación de `WorkoutProvider` que se conecta a Huawei Health Kit mediante OAuth.
- **Servicio_De_Sincronizacion**: Componente del Backend que ejecuta la descarga periódica de entrenamientos desde un `WorkoutProvider`.
- **Token_De_Refresco**: Credencial OAuth persistida que permite renovar el acceso a Huawei Health Kit sin reautenticación del usuario.
- **Zona_De_FC**: Rango de frecuencia cardiaca calculado a partir de la frecuencia cardiaca del usuario.
- **Carga_De_Entrenamiento**: Métrica agregada que estima el esfuerzo de un entrenamiento o periodo.

## Requirements

### Requirement 1: Onboarding y configuración de Huawei Health Kit

**User Story:** Como desarrollador del sistema, quiero configurar el acceso a Huawei Health Kit mediante OAuth, para poder sincronizar los entrenamientos reales del usuario cuando Huawei apruebe el acceso.

#### Acceptance Criteria

1. THE Backend SHALL almacenar `client_id`, `client_secret` y `redirect_uri` de Huawei como variables de entorno.
2. WHERE existan credenciales de Huawei configuradas, THE Backend SHALL exponer un flujo OAuth que obtenga un Token_De_Refresco de Huawei Health Kit.
3. WHEN el flujo OAuth de Huawei completa correctamente, THE Backend SHALL persistir el Token_De_Refresco en la Base_De_Datos.
4. El modo personal comienza con el conector periódico apagado. Los ejemplos sintéticos requieren modo demo explícito y una base separada.

### Requirement 2: Cimientos del proyecto y entorno de desarrollo

**User Story:** Como desarrollador del sistema, quiero una estructura de proyecto y un entorno local reproducibles, para poder desarrollar y ejecutar el sistema de forma consistente.

#### Acceptance Criteria

1. THE Compi SHALL organizar el repositorio en los directorios `ios/`, `backend/`, `frontend/` y `docs/`.
2. THE Compi SHALL proporcionar una configuración de docker-compose que levante una instancia de Base_De_Datos PostgreSQL para desarrollo local.
3. THE Backend SHALL leer su configuración desde variables de entorno.
4. THE Compi SHALL incluir un archivo README con instrucciones de instalación y ejecución, y un archivo `.gitignore`.

### Requirement 3: Modelo de datos de entrenamientos

**User Story:** Como usuario, quiero que mis entrenamientos se almacenen de forma estructurada según su tipo, para poder consultar tanto datos de cardio como de fuerza.

#### Acceptance Criteria

1. THE Base_De_Datos SHALL almacenar cada Workout con tipo (cardio o fuerza), duración, frecuencia cardiaca y calorías.
2. WHERE un Workout es de tipo cardio, THE Base_De_Datos SHALL almacenar datos de GPS, ritmo (pace) y parciales (splits).
3. WHERE un Workout es de tipo fuerza, THE Base_De_Datos SHALL almacenar un resumen del entrenamiento de fuerza.
4. THE Base_De_Datos SHALL permitir asociar a un Workout de fuerza ejercicios con peso, repeticiones, descanso y esfuerzo independientes por serie.
5. WHEN un usuario registra manualmente sus ejercicios, THE Backend SHALL persistir sus series asociadas al Workout correspondiente.

### Requirement 4: Modelo de periodización

**User Story:** Como usuario, quiero planificar mis entrenamientos mediante periodización, para poder estructurar mi progreso en macrociclos, mesociclos y microciclos.

#### Acceptance Criteria

1. THE Base_De_Datos SHALL almacenar Macrociclos, Mesociclos, Microciclos y Sesiones_Planificadas con una relación jerárquica de Macrociclo a Mesociclo a Microciclo a Sesion_Planificada.
2. THE Base_De_Datos SHALL permitir asociar una Sesion_Planificada con un Workout real.
3. WHEN un usuario crea una Sesion_Planificada dentro de un Microciclo, THE Backend SHALL persistir la Sesion_Planificada vinculada a ese Microciclo.

### Requirement 5: Abstracción de proveedor de entrenamientos

**User Story:** Como desarrollador del sistema, quiero una abstracción de proveedor de entrenamientos, para poder desarrollar con datos simulados y conectar Huawei real sin cambiar el resto del sistema.

#### Acceptance Criteria

1. THE Backend SHALL definir una interfaz WorkoutProvider con operaciones de autenticación y descarga de entrenamientos.
2. THE Backend SHALL proporcionar un MockProvider que implemente WorkoutProvider y devuelva datos de prueba realistas.
3. THE Backend SHALL proporcionar un HuaweiProvider que implemente WorkoutProvider y se conecte a Huawei Health Kit.
4. WHERE el proveedor activo es el MockProvider, THE Servicio_De_Sincronizacion SHALL operar sin requerir credenciales de Huawei.

### Requirement 6: Sincronización de entrenamientos con deduplicación

**User Story:** Como usuario, quiero que mis nuevos entrenamientos se descarguen automáticamente sin duplicados, para mantener mi historial actualizado y consistente.

#### Acceptance Criteria

1. THE Servicio_De_Sincronizacion SHALL descargar los entrenamientos nuevos desde el WorkoutProvider activo mediante un trabajo en segundo plano.
2. IF un entrenamiento descargado tiene un identificador que ya existe en la Base_De_Datos, THEN THE Servicio_De_Sincronizacion SHALL omitir su inserción.
3. WHEN se descarga un entrenamiento con un identificador no existente, THE Servicio_De_Sincronizacion SHALL persistirlo como un nuevo Workout.
4. IF el Token_De_Refresco está expirado, THEN THE HuaweiProvider SHALL renovar el acceso usando el Token_De_Refresco antes de descargar entrenamientos.

### Requirement 7: API REST de entrenamientos, métricas y planes

**User Story:** Como consumidor del frontend, quiero endpoints REST para entrenamientos, métricas y planes, para poder mostrar y gestionar los datos del usuario.

#### Acceptance Criteria

1. THE Backend SHALL exponer endpoints REST para consultar entrenamientos (workouts).
2. THE Backend SHALL exponer endpoints REST para consultar métricas (metrics).
3. THE Backend SHALL exponer endpoints REST para gestionar planes de periodización (plans).
4. WHEN se solicita un recurso inexistente a través de la API, THE Backend SHALL responder con un código de error que indique que el recurso no existe.

### Requirement 8: Cálculo de métricas de entrenamiento

**User Story:** Como usuario, quiero ver métricas calculadas de mis entrenamientos, para poder evaluar mi rendimiento y esfuerzo.

#### Acceptance Criteria

1. WHEN se solicitan las métricas de un Workout con datos de frecuencia cardiaca, THE Backend SHALL calcular las Zonas_De_FC correspondientes.
2. THE Backend SHALL calcular el volumen de entrenamiento a partir de los entrenamientos registrados.
3. THE Backend SHALL calcular la Carga_De_Entrenamiento a partir de los entrenamientos registrados.

### Requirement 9: Lógica de progresión y comparación planificado vs. real

**User Story:** Como usuario, quiero una progresión planificada y la comparación con lo realmente ejecutado, para poder ajustar mi entrenamiento.

#### Acceptance Criteria

1. WHERE un Mesociclo tiene configurada una progresión por incremento porcentual semanal, THE Backend SHALL calcular la carga objetivo de cada Microciclo aplicando dicho incremento respecto al Microciclo anterior.
2. WHERE un Microciclo está marcado como semana de descarga (deload), THE Backend SHALL reducir la carga objetivo de ese Microciclo respecto al Microciclo anterior.
3. WHEN una Sesion_Planificada está asociada a un Workout real, THE Backend SHALL calcular la comparación entre los valores planificados y los valores ejecutados.

### Requirement 10: Frontend PWA

**User Story:** Como usuario, quiero una aplicación web instalable que muestre mis datos de entrenamiento, para poder consultarlos cómodamente desde mis dispositivos.

#### Acceptance Criteria

1. THE Frontend SHALL ser una PWA instalable.
2. THE Frontend SHALL mostrar un panel general (dashboard) con un resumen de los entrenamientos.
3. WHEN el usuario consulta un Workout de tipo cardio, THE Frontend SHALL mostrar el mapa, las Zonas_De_FC y el ritmo (pace).
4. WHEN el usuario consulta un Workout de tipo fuerza, THE Frontend SHALL mostrar el volumen, el progreso y un formulario de registro manual.
5. THE Frontend SHALL mostrar una vista de plan con los niveles de macrociclo, mesociclo y microciclo y su progreso.

### Requirement 11. Operación personal y entrega

1. El panel y PostgreSQL se ejecutan en el computador. El único servicio ofrecido al iPhone por la red local es el receptor de lotes HTTPS emparejado.
2. CI valida los componentes modificados con datos sintéticos. El despliegue de AWS y la promoción de modelos tienen ciclos independientes de la publicación de la aplicación.

### Requirement 12. Observaciones y privacidad

1. Una persona selecciona qué leer de Salud: entrenamientos, frecuencia cardiaca, sueño y peso corporal. Cada muestra conserva su UUID, categoría, aplicación de origen, intervalo y unidad o categoría normalizada.
2. Al perder la conexión, un lote pendiente se reintenta con el mismo contenido. El cursor y las altas, correcciones y bajas se confirman juntos. Una secuencia omitida o incompatible requiere reconciliación.
3. El panel muestra muestras y última recepción por categoría. La ausencia de muestras es una cobertura desconocida para inferir actividad o recuperación.
4. La telemetría técnica registra resultado y latencia. Los datos de salud, credenciales e identificadores individuales quedan en el circuito local protegido.

### Requirement 13. Plan semanal y evaluación

1. La persona declara ventanas semanales en su zona horaria, acceso al gimnasio y excepciones por fecha. Puede revisar los motivos y los cambios de las sesiones de fuerza, carrera y caminata.
2. La prescripción y el registro realizado son independientes. Un ejercicio admite series distintas de peso, repeticiones, descansos y esfuerzo.
3. El primer experimento retrospectivo compara estimadores de duración sobre las mismas sesiones elegibles de una sola fuente. Registra tamaño, error en minutos y frecuencia de subestimación. Con historial insuficiente se presenta esa limitación.
4. Futuras estimaciones de bienestar deben incluir evidencia, incertidumbre y la respuesta de la persona antes de influir en otros planes. Los objetivos físicos y el peso corporal se gestionan como datos personales. Una variación de peso por sí sola no determina grasa o masa muscular.

## Alcance

Una persona, un iPhone y un computador en la primera versión. La validación de extremo a extremo con hardware, los permisos reales por categoría, los servicios compartidos y el laboratorio en AWS tienen hitos propios en [tasks.md](tasks.md).
