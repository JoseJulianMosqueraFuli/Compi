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

## Emparejar por Wi-Fi

1. Determina el nombre Bonjour del Mac con `scutil --get LocalHostName` y añade `.local`. Usa siempre ese nombre para el mismo receptor.
2. Prepara un certificado TLS para ese nombre. Por ejemplo, con [mkcert](https://github.com/FiloSottile/mkcert) instalado, ejecuta desde la raíz:

   ```sh
   umask 077
   mkdir -p .compi-local/tls
   mkcert -install
   mkcert -cert-file .compi-local/tls/server.pem -key-file .compi-local/tls/server-key.pem "$(scutil --get LocalHostName).local"
   ```

   Transfiere al iPhone solo el certificado público `rootCA.pem` del directorio que indica `mkcert -CAROOT`. Verifica que corresponde a tu CA local, instala el perfil y habilita confianza en Ajustes → General → Información → Ajustes de confianza de certificados. Protege en el Mac ambas claves privadas. [Confianza de certificados en iOS](https://support.apple.com/102390).
3. Genera un secreto local con `openssl rand -hex 32` y establece ese valor en `HEALTHKIT_SYNC_TOKEN` en `backend/.env`. Restringe el archivo con `chmod 600 backend/.env`. Mantén `LEGACY_SYNC_MODE=off` en tu base personal.
4. Desde `backend/`, con su entorno activo, inicia el receptor. Sustituye la dirección de ejemplo por la IPv4 Wi-Fi del computador, visible en los ajustes de red. El puerto elegido debe estar permitido en esa red.

   ```sh
   uvicorn app.mobile:app --host 192.168.1.50 --port 8443 --no-proxy-headers --no-access-log \
     --ssl-keyfile ../.compi-local/tls/server-key.pem --ssl-certfile ../.compi-local/tls/server.pem
   ```

5. Instala y configura [Compi para iPhone](../ios/README.md). Introduce el nombre HTTPS, el puerto y el secreto. Selecciona las categorías y pulsa **Sincronizar ahora**. La sincronización actual es en primer plano. Un lote confirmado permite avanzar el ancla local. Si se corta el envío el iPhone conserva los cambios pendientes.

## Comprobar y recuperar

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
