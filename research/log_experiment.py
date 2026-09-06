#!/usr/bin/env python3
"""Log a reproducible experiment summary into MLflow.

Usage:
  python research/log_experiment.py run.json

Expected JSON keys are intentionally generic; unknown numeric fields are logged as metrics,
strings/bools as parameters.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import mlflow


def git_commit() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    except Exception:
        return "unknown"


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: log_experiment.py run.json")
    path = Path(sys.argv[1])
    payload = json.loads(path.read_text(encoding="utf-8"))

    uri = os.getenv("MLFLOW_TRACKING_URI", "http://127.0.0.1:5000")
    mlflow.set_tracking_uri(uri)
    mlflow.set_experiment(payload.pop("experiment", "trading-lab"))

    with mlflow.start_run(run_name=payload.pop("run_name", path.stem)):
        mlflow.log_param("git_commit", git_commit())
        mlflow.log_artifact(str(path))
        for key, value in payload.items():
            if isinstance(value, bool) or isinstance(value, str):
                mlflow.log_param(key, value)
            elif isinstance(value, (int, float)):
                mlflow.log_metric(key, float(value))
            else:
                mlflow.log_param(key, json.dumps(value, sort_keys=True))


if __name__ == "__main__":
    main()
