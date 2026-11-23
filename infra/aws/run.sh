#!/usr/bin/env bash
# Run from the operator's shell after deploying template.json.
set -euo pipefail

if [[ $# != 2 || -z $1 || -z $2 ]]; then
  echo "Uso: bash infra/aws/run.sh NOMBRE_STACK ID_DE_EJECUCION" >&2
  exit 2
fi
stack=$1
run_id=$2
region=${COMPI_AWS_REGION:-us-east-1}
labaws() { AWS_PAGER='' aws --profile personal --region "$region" "$@"; }

outputs=$(labaws cloudformation describe-stacks --stack-name "$stack" --query 'Stacks[0].Outputs' --output json |
  jq -e 'map({key: .OutputKey, value: .OutputValue}) | from_entries')
cluster=$(jq -er '.Cluster' <<< "$outputs")
definition=$(jq -er '.Definition' <<< "$outputs")
network=$(jq -er '.Network' <<< "$outputs")
group=$(jq -er '.LogGroup' <<< "$outputs")

launch=$(labaws ecs run-task --cluster "$cluster" --task-definition "$definition" \
  --launch-type FARGATE --count 1 --network-configuration "$network" --client-token "$run_id" \
  --tags key=Project,value=Compi key=Lab,value=synthetic --output json)
if ! jq -e '(.failures | length) == 0 and (.tasks | length) == 1' <<< "$launch" >/dev/null; then
  jq '.failures' <<< "$launch" >&2
  exit 1
fi
task=$(jq -er '.tasks[0].taskArn' <<< "$launch")
echo "Tarea $task" >&2
labaws ecs wait tasks-stopped --cluster "$cluster" --tasks "$task"
result=$(labaws ecs describe-tasks --cluster "$cluster" --tasks "$task" --output json)
if ! jq -e '.tasks[0].containers[] | select(.name == "experiment") | .exitCode == 0' \
    <<< "$result" >/dev/null; then
  jq '{failures, tasks: [.tasks[] | {stoppedReason, containers: [.containers[] | {name, reason, exitCode}]}]}' \
    <<< "$result" >&2
  exit 1
fi
# Poll for log delivery, which can lag the STOPPED event.
for attempt in {1..10}; do
  if messages=$(labaws logs get-log-events --log-group-name "$group" \
      --log-stream-name "synthetic/experiment/${task##*/}" --start-from-head --output json) &&
      report=$(jq -er '[.events[].message] | join("\n") | fromjson | select(.synthetic == true)' <<< "$messages"); then
    printf '%s\n' "$report"
    exit 0
  fi
  sleep 2
done
echo "La tarea terminó correctamente. Revisa la entrega de su informe en el grupo $group." >&2
exit 1
