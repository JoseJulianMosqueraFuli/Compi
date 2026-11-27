# Operar Compi en el computador y el iPhone

## Preparar el computador

Se necesita Python 3.11 o posterior, PostgreSQL 16 y el gestor pnpm indicado en el frontend. Para el iPhone se necesita Xcode completo con capacidad HealthKit y firma para el dispositivo. Para probar los contratos y el experimento sintético se puede utilizar el backend por separado.

Desde la raíz del repositorio, inicia PostgreSQL y aplica las migraciones. Una base usada anteriormente en modo demo puede contener ejemplos. Usa una base dedicada para tu historial personal.

```sh
docker compose up -d db
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
test -f .env || cp .env.example .env
alembic upgrade head
uvicorn app.main:app --host 127.0.0.1 --port 8000 --no-access-log
```

En otra terminal, desde la raíz:

```sh
cd frontend
pnpm install --frozen-lockfile
pnpm dev --hostname 127.0.0.1
```

Abre [el panel](http://localhost:3000) y [Semana](http://localhost:3000/semana) en el computador. El panel necesita acceso al API en localhost. PostgreSQL se publica únicamente en la interfaz de loopback. Para salud personal usa cifrado de disco en el computador y copias protegidas bajo tu control.

En **Historial diario**, selecciona una categoría, una fuente y un día. El pulso y el peso muestran puntos individuales; la tabla despliega las horas originales. Sueño y entrenamientos aparecen como intervalos, incluidos los que atraviesan la medianoche. La zona horaria del navegador aparece junto a las muestras. En **Entrenamientos importados → Registrar o vincular**, confirma si quieres crear un registro editable o asociar la muestra a una actividad existente. El registro de fuerza permite anotar el peso levantado, repeticiones y descanso por serie.

## Emparejar por Wi-Fi

1. En los ajustes Wi-Fi del Mac consulta la IPv4 de tu red. El ejemplo usa `192.168.1.50`; sustitúyela en los comandos. Elige un nombre Bonjour estable o reserva la IP en tu router. El iPhone asocia el progreso de la importación a la dirección que guardes.
2. Genera el certificado desde la raíz. El script incluye el nombre Bonjour y la IP privada para que puedas usar cualquiera de los dos al emparejar por primera vez.

   ```sh
   bash scripts/prepare-iphone-tls.sh "$(scutil --get LocalHostName).local" 192.168.1.50
   ```

   Envía al iPhone por AirDrop el certificado público `.compi-local/tls/Compi-CA.cer`. Compara su huella SHA-256 con la que imprimió el script, instala el perfil y activa la confianza en Ajustes → General → Información → Ajustes de confianza de certificados. La clave privada del servidor permanece en el Mac. El script descarta la clave de firma de la autoridad después de emitir el certificado del servidor, válido durante 90 días. Para renovarlo, detén el receptor, mueve el directorio TLS anterior a un lugar privado y repite este paso. Tras comprobar el nuevo certificado, retira el perfil anterior del iPhone. [Confianza de certificados en iOS](https://support.apple.com/102390).
3. Genera un secreto local con `openssl rand -hex 32` y establece ese valor en `HEALTHKIT_SYNC_TOKEN` en `backend/.env`. Restringe el archivo con `chmod 600 backend/.env`. Mantén `LEGACY_SYNC_MODE=off` en tu base personal.
4. Desde `backend/`, con su entorno activo, inicia el receptor. Sustituye la dirección de ejemplo por la IPv4 Wi-Fi del computador, visible en los ajustes de red. El puerto elegido debe estar permitido en esa red.

   ```sh
   uvicorn app.mobile:app --host 192.168.1.50 --port 8443 --no-proxy-headers --no-access-log \
     --ssl-keyfile ../.compi-local/tls/server-key.pem --ssl-certfile ../.compi-local/tls/server.pem
   ```

5. Instala y configura [Compi para iPhone](../ios/README.md). Con ambos equipos en la misma Wi-Fi, guarda la dirección HTTPS y el secreto. Pulsa **Probar conexión** y concede el acceso a la red local cuando lo solicite iOS. El mensaje de éxito confirma que el iPhone llega al receptor y que este puede abrir el esquema de salud. Después, elige las categorías y pulsa **Sincronizar ahora** para autorizar Salud. La sincronización ocurre en primer plano y conserva los lotes pendientes si se corta el envío.

## Estado de la primera sincronización

Verificación del **27 de noviembre de 2026** en el Mac de desarrollo. La primera importación desde el iPhone físico sigue pendiente.

| Tramo | Resultado observado | Qué permite concluir |
|---|---|---|
| Panel y API personal | La portada, `/semana` y `GET /ready` respondieron HTTP 200. | El panel está disponible en el Mac y la API alcanza PostgreSQL. |
| Recepción de Salud | `GET /api/healthkit/coverage` devolvió cuatro categorías, cero con lote recibido y cero muestras en total. | La base personal aún no registra una importación. |
| Mac hacia el receptor por su IP Wi-Fi | El receptor escuchaba en 8443. La negociación TLS se cortó antes de enviar el token. | El intento terminó antes de la autenticación. La causa del cierre y el resultado desde el iPhone físico siguen pendientes. |

Para cerrar este hito, comprueba primero el acceso desde Safari y el emparejamiento desde Compi como se indica abajo. Luego sincroniza **Entrenamientos** con el permiso de lectura activo. Actualiza el panel y contrasta la fuente y el intervalo de un entrenamiento con Salud. Repite la sincronización sin cambios en Salud y verifica que el entrenamiento aparece una sola vez.

## Comprobar y recuperar

1. **Desde el Mac.** Con el receptor en marcha, ejecuta estos comandos desde la raíz y sustituye la IP por la del certificado. La prueba usa la CA del proyecto y el token del backend. Un HTTP 200 confirma el emparejamiento desde ese Mac. Si falla, el mensaje indica si el problema apareció al resolver el nombre, abrir TCP, negociar TLS o comprobar el token, el protocolo o el almacenamiento.

   ```sh
   cd backend
   .venv/bin/python -m app.check_healthkit https://192.168.1.50:8443
   ```

2. **Desde Safari en el iPhone.** Una vez instalada y activada la confianza de la CA, abre `https://192.168.1.50:8443/api/healthkit/connection` en la misma Wi-Fi. Usa la IP de tu Mac. Puedes probar antes de instalar Xcode. La respuesta `{"detail":"pairing required"}` (HTTP 401) confirma que ese iPhone llegó al receptor por HTTPS. Mantén el token fuera de la URL.
3. **Desde Compi en el iPhone.** Pulsa **Probar conexión** con la dirección y el token guardados. iOS controla el permiso de red local de la app. En el Mac, un servicio puede escuchar y aceptar conexiones TCP entrantes sin ese permiso. Si TLS se corta antes de presentar el certificado, compara lo que ocurre en Safari con el resultado del Mac y comprueba que ambos están en una red que admite conexiones entre dispositivos. [Privacidad de red local de Apple](https://developer.apple.com/documentation/technotes/tn3179-understanding-local-network-privacy)

- `GET /health` comprueba el proceso y `GET /ready` la conexión del API local a la base. En el panel comprueba fuente, categorías y última recepción. El conector Huawei directo y su autorización son independientes de HealthKit.
- Un 401 indica que conviene revisar el token. Para rotarlo, cambia el secreto en el Mac, reinicia el receptor y guarda el nuevo token en el iPhone para la misma dirección. Un 503 puede indicar un emparejamiento sin configurar o almacenamiento indisponible.
- Ante 409, revisa primero que estás enviando a la base original. Para reimportar una categoría tras reinstalar la app o restaurar un cursor incompatible, detén el receptor y sigue [Restablecer una categoría](../ios/README.md#restablecer-una-categoría). El comando local `python -m app.reset_healthkit --kind workout --confirm` elimina de esa base las muestras importadas y el cursor de la categoría indicada. Un nuevo envío recupera lo que el iPhone aún pueda leer.
- Para comprobar un respaldo, detén escrituras, usa `pg_dump -Fc` con tu conexión local hacia almacenamiento cifrado y restaura con `pg_restore` en una base vacía distinta. Verifica conteos por categoría, versión de Alembic y planes existentes antes de cambiar `DATABASE_URL`. Controla también los respaldos y los experimentos al retirar datos.

## Evaluar la duración

Desde `backend/`, ejecuta el experimento reproducible sin base de datos:

```sh
python -m app.experiment --synthetic
```

Para evaluar tus sesiones, pasa a `--source` un único identificador de origen de entrenamientos del panel. El objetivo son los minutos transcurridos entre inicio y fin del registro, incluidas pausas. Para cada sesión se usan las anteriores ya terminadas de esa fuente. Se compara la mediana de las últimas ocho sesiones con la mediana de las últimas ocho de esa actividad. Ambas se evalúan en las mismas sesiones, con un mínimo de tres observaciones anteriores de esa actividad. La salida incluye error absoluto medio, subestimaciones, sesiones evaluadas y huella del conjunto. Es una evaluación retrospectiva del historial visible en el momento de calcularla.

Para conservar una corrida en **MLflow local**, inicia un tracking server independiente en loopback. Desde la raíz del repo y con MLflow instalado en un entorno aparte:

```sh
mkdir -p .compi-local/mlflow
mlflow server --host 127.0.0.1 --port 5050 --backend-store-uri sqlite:///.compi-local/mlflow/tracking.db \
  --default-artifact-root "$(pwd)/.compi-local/mlflow/artifacts"
```

Desde `backend/`, usa `python -m app.experiment --synthetic --mlflow-experiment-id 0`. El cliente envía parámetros, huella y métricas agregadas al servidor local. En [MLflow](http://127.0.0.1:5050) puedes comparar las ejecuciones. Los modelos candidatos requieren una decisión explícita antes de alterar la planificación. [API de tracking](https://mlflow.org/docs/latest/ml/tracking/tracking-api/).
