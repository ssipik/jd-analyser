"""MLflow tracing for Anthropic API calls.

`enable_tracing` points MLflow at the configured tracking server, selects the experiment,
and turns on Anthropic autologging — which patches the SDK so every `messages.create`
call is captured as a trace (prompt, tools, response, token usage, latency) with no
per-call instrumentation. It is idempotent and fails soft: if the server is unreachable
or MLflow misbehaves, analysis still runs and traces are simply dropped.
"""
from __future__ import annotations

import logging

logger = logging.getLogger("jd_analyser")

_enabled = False


def enable_tracing(tracking_uri: str, experiment: str) -> bool:
    """Configure MLflow and enable Anthropic autolog. Returns True if active."""
    global _enabled
    if _enabled:
        return True
    try:
        import mlflow

        mlflow.set_tracking_uri(tracking_uri)
        mlflow.set_experiment(experiment)
        mlflow.anthropic.autolog()
        _enabled = True
        logger.info(f"MLflow tracing enabled → {tracking_uri} (experiment: {experiment})")
        return True
    except Exception as exc:  # never let tracing break the pipeline
        logger.warning(f"MLflow tracing disabled — could not initialise: {exc}")
        return False
