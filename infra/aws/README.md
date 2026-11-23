# Laboratorio AWS del recomendador

[La plantilla](template.json) prepara un clúster ECS y una definición Fargate Linux x86_64 de 0,25 vCPU y 512 MiB. Cada invocación de [run.sh](run.sh) ejecuta `python -m app.experiment --synthetic` una vez. El informe de duración se escribe en CloudWatch Logs y puede guardarse en el equipo para comparar ejecuciones. El contenedor carece de rol de tarea, volúmenes, puertos y credenciales de Compi. Fargate usa su propio rol para descargar una imagen privada de ECR por digest y escribir logs.

## Preparación

Usa la raíz del repositorio, una terminal Bash, Docker Buildx, AWS CLI y jq. El perfil `personal` necesita acceso al repositorio ECR, permisos para crear y eliminar los recursos de la plantilla, lanzar y consultar tareas, pasar el rol de ejecución a ECS y leer sus logs. Selecciona una **subred IPv4 privada existente** que ya tenga salida HTTPS por NAT, o endpoints de ECR API, ECR DKR, S3 (capas de imagen) y CloudWatch Logs accesibles desde el grupo de seguridad de la tarea. La tarea usa dirección privada. Comprueba la conectividad y el costo de esa red con su propietario. [Red de Fargate](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/fargate-task-networking.html) · [Rol de ejecución](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/task_execution_IAM_role.html)

Asigna los siguientes valores en tu terminal. `COMPI_IMAGE_DIGEST` identifica la imagen del backend de Compi construida para `linux/amd64` en un repositorio privado existente de la misma región y cuenta.

```bash
export COMPI_AWS_REGION=us-east-1
export COMPI_STACK=compi-synthetic-lab
export COMPI_ECR_REPO=compi-backend
export COMPI_SUBNET_ID='<subred privada del laboratorio>'
export COMPI_IMAGE_DIGEST='<sha256:...>'
labaws() { AWS_PAGER='' aws --profile personal --region "$COMPI_AWS_REGION" "$@"; }
```

Si necesitas publicar la imagen, el siguiente bloque usa exclusivamente los archivos versionados de `backend/`. Selecciona una revisión que incluya `app.experiment`. Cada compilación recibe una etiqueta única. El digest se toma de la salida de Buildx.

```bash
set -euo pipefail
compi_build=$(mktemp -d)
git archive HEAD:backend | tar -x -C "$compi_build"
test -f "$compi_build/app/experiment.py"
compi_uri=$(labaws ecr describe-repositories --repository-names "$COMPI_ECR_REPO" \
  --query 'repositories[0].repositoryUri' --output text)
labaws ecr get-login-password | docker login --username AWS --password-stdin "${compi_uri%%/*}"
compi_tag="$(git rev-parse --short HEAD)-$(uuidgen | tr '[:upper:]' '[:lower:]')"
docker buildx build --platform linux/amd64 --provenance=false --push \
  --tag "$compi_uri:$compi_tag" --metadata-file "$compi_build/result.json" "$compi_build"
COMPI_IMAGE_DIGEST=$(jq -er '."containerimage.digest"' "$compi_build/result.json")
```

## Desplegar y ejecutar

La pila utiliza la VPC de la subred seleccionada y verifica que la imagen por digest existe antes del despliegue. CloudFormation administra el clúster, la definición de tarea, el rol de ejecución, un grupo de seguridad sin entrada y el grupo de logs con retención de tres días.

```bash
set -euo pipefail
compi_vpc=$(labaws ec2 describe-subnets --subnet-ids "$COMPI_SUBNET_ID" \
  --query 'Subnets[0].VpcId' --output text)
labaws ecr describe-images --repository-name "$COMPI_ECR_REPO" \
  --image-ids "imageDigest=$COMPI_IMAGE_DIGEST" --query 'imageDetails[0].imageDigest'
time labaws cloudformation deploy --stack-name "$COMPI_STACK" \
  --template-file infra/aws/template.json --capabilities CAPABILITY_IAM \
  --parameter-overrides "VpcId=$compi_vpc" "SubnetId=$COMPI_SUBNET_ID" \
    "RepositoryName=$COMPI_ECR_REPO" "ImageDigest=$COMPI_IMAGE_DIGEST" \
  --tags Project=Compi Lab=synthetic --no-fail-on-empty-changeset
compi_run=$(uuidgen)
bash infra/aws/run.sh "$COMPI_STACK" "$compi_run" > "/tmp/compi-$compi_run.json"
jq '{synthetic, evaluated_sessions, baseline, by_activity, dataset_sha256}' "/tmp/compi-$compi_run.json"
```

Ante un corte, reintenta con el mismo `compi_run` y la misma definición durante la ventana de idempotencia de ECS. Para un experimento independiente genera otro identificador. El script comprueba los fallos de lanzamiento, el código de salida y el informe sintético. Compara la misma huella del dataset, el error en minutos y las subestimaciones antes de promover un cambio. Conserva el digest de imagen junto al informe.

## Cerrar y comprobar el costo

1. Guarda el informe antes de eliminar la pila. Los logs temporales se eliminan con ella. Si interrumpiste la espera, localiza la tarea por el ARN que imprimió `run.sh` y espera a que termine. Para cancelar una tarea activa, usa `ecs stop-task` con ese clúster y ARN.
2. Desde la misma terminal elimina únicamente la pila del laboratorio:

   ```bash
   labaws cloudformation delete-stack --stack-name "$COMPI_STACK"
   labaws cloudformation wait stack-delete-complete --stack-name "$COMPI_STACK"
   ```

3. En Cost Explorer revisa la región, ventana del ensayo y servicios, y las etiquetas `Project=Compi` y `Lab=synthetic` si están activadas para asignación de costos. Registra el tiempo del despliegue y la duración facturada de Fargate desde la descarga de imagen, ingestión de logs y almacenamiento en ECR. Revisa también tráfico y cargos por hora de NAT o endpoints compartidos. El costo puede tardar en aparecer. La imagen, el repositorio, la VPC y la subred pertenecen al operador y conservan su propio ciclo de vida. [Precios de Fargate](https://aws.amazon.com/fargate/pricing/) · [Precios de VPC](https://aws.amazon.com/vpc/pricing/)

Para validar la plantilla localmente ejecuta `cfn-lint -r us-east-1 -t infra/aws/template.json`.
