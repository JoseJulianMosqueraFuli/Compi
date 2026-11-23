"""Local CLI for evaluating session duration and optionally recording aggregates in MLflow."""

import argparse
import hashlib
import json
from datetime import UTC, datetime, timedelta
from time import time

import httpx
from sqlmodel import Session

from app.db import engine
from app.services.duration_experiment import (
    HISTORY_SIZE,
    VERSION,
    WARMUP,
    Evaluation,
    RecordedSession,
    evaluate_sessions,
    source_sessions,
)


def dataset_digest(records: list[RecordedSession]) -> str:
    def utc(value: datetime) -> str:
        return (value if value.tzinfo else value.replace(tzinfo=UTC)).astimezone(UTC).isoformat()

    rows = sorted((utc(r.start), utc(r.end), r.activity) for r in records)
    return hashlib.sha256(json.dumps(rows, separators=(",", ":")).encode()).hexdigest()


def track(client: httpx.Client, experiment_id: str, result: Evaluation, digest: str, synthetic: bool) -> str:
    run = client.post("runs/create", json={"experiment_id": experiment_id, "run_name": VERSION})
    run.raise_for_status()
    run_id = run.json()["run"]["info"]["run_id"]
    timestamp = int(time() * 1000)
    measures = {
        "observed_sessions": result.observed_sessions,
        "evaluated_sessions": result.evaluated_sessions,
    }
    for name, scores in (("baseline", result.baseline), ("by_activity", result.by_activity)):
        if scores:
            measures[f"{name}_mae_minutes"] = scores.mae_minutes
            measures[f"{name}_underestimated"] = scores.underestimated
    params = {
        "evaluation_version": VERSION,
        "dataset_sha256": digest,
        "history_size": str(HISTORY_SIZE),
        "minimum_history": str(WARMUP),
        "data": "synthetic" if synthetic else "personal",
        "target": "elapsed_minutes",
    }
    try:
        client.post(
            "runs/log-batch",
            json={
                "run_id": run_id,
                "params": [{"key": k, "value": v} for k, v in params.items()],
                "metrics": [
                    {"key": k, "value": v, "timestamp": timestamp, "step": 0} for k, v in measures.items()
                ],
            },
        ).raise_for_status()
    except httpx.HTTPError:
        client.post(
            "runs/update", json={"run_id": run_id, "status": "FAILED", "end_time": int(time() * 1000)}
        )
        raise
    client.post(
        "runs/update",
        json={
            "run_id": run_id,
            "status": "FINISHED",
            "end_time": int(time() * 1000),
        },
    ).raise_for_status()
    return run_id


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    data = parser.add_mutually_exclusive_group(required=True)
    data.add_argument("--synthetic", action="store_true", help="Use the deterministic example.")
    data.add_argument("--source", help="A workout source from the local dashboard.")
    parser.add_argument("--mlflow-experiment-id", help="Log aggregates to MLflow on 127.0.0.1:5050.")
    args = parser.parse_args()
    if args.synthetic:
        base = datetime(2026, 1, 1, tzinfo=UTC)
        records = []
        for day in range(18):
            activity, minutes = (("walk", 25), ("strength", 55), ("run", 40))[day % 3]
            start = base + timedelta(days=day)
            records.append(RecordedSession(start, start + timedelta(minutes=minutes + day % 5), activity))
    else:
        with Session(engine) as session:
            records = source_sessions(session, args.source)
    result = evaluate_sessions(records)
    digest = dataset_digest(records)
    report = result.model_dump() | {"dataset_sha256": digest, "synthetic": args.synthetic}
    if args.mlflow_experiment_id:
        with httpx.Client(base_url="http://127.0.0.1:5050/api/2.0/mlflow/", trust_env=False) as client:
            report["mlflow_run"] = track(client, args.mlflow_experiment_id, result, digest, args.synthetic)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
