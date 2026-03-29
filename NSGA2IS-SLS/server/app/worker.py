from __future__ import annotations

import argparse
import json
import logging
import os
import signal
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .application.services.async_schedule_service import mark_completed, mark_failed, mark_running
from .application.use_cases.generate_schedule import GenerateScheduleUseCase
from .config import get_settings
from .domain.schemas import ScheduleRunRequestDTO


REQUEST_ID_ENV_NAMES = ("REQUEST_ID", "WORKER_REQUEST_ID")
PAYLOAD_ENV_NAMES = (
    "WORKER_EVENT_JSON",
    "WORKER_EVENT",
    "TASK_PAYLOAD",
    "EVENT_PAYLOAD",
    "INPUT_PAYLOAD",
)
WORKER_MAX_RUNTIME_SECONDS_ENV = "WORKER_MAX_RUNTIME_SECONDS"
LOG_LEVEL_ENV = "LOG_LEVEL"

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class WorkerJob:
    request_id: str
    payload: dict[str, Any]


def _configure_logging() -> None:
    level_name = os.getenv(LOG_LEVEL_ENV, "INFO").upper().strip()
    level = getattr(logging, level_name, logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


def _configure_runtime_timeout() -> None:
    raw_value = os.getenv(WORKER_MAX_RUNTIME_SECONDS_ENV, "0").strip()
    if not raw_value:
        return

    timeout_seconds = int(float(raw_value))
    if timeout_seconds <= 0:
        return

    def _handle_timeout(_signum, _frame) -> None:
        raise TimeoutError(f"Worker exceeded max runtime of {timeout_seconds} seconds")

    signal.signal(signal.SIGALRM, _handle_timeout)
    signal.alarm(timeout_seconds)
    logger.info("Configured worker runtime timeout: %s seconds", timeout_seconds)


def _clear_runtime_timeout() -> None:
    try:
        signal.alarm(0)
    except Exception:
        pass


def _read_text_source(source: str) -> str:
    text = source.strip()
    if not text:
        return text

    if text[:1] in {"{", "["}:
        return text

    path = Path(text)
    if path.is_file():
        return path.read_text(encoding="utf-8")

    return text


def _load_json_value(raw_value: Any) -> Any:
    if isinstance(raw_value, (dict, list)):
        return raw_value
    if raw_value is None:
        raise ValueError("Payload is empty")

    text = str(raw_value).strip()
    if not text:
        raise ValueError("Payload is empty")
    return json.loads(text)


def _load_json_from_cli_or_env(raw_value: str | None) -> dict[str, Any] | None:
    if raw_value is None:
        return None
    loaded = _load_json_value(_read_text_source(raw_value))
    if not isinstance(loaded, dict):
        raise ValueError("Worker input must be a JSON object")
    return loaded


def _load_job_source(argv: list[str] | None = None) -> tuple[dict[str, Any], str | None]:
    parser = argparse.ArgumentParser(description="Event-driven NSGA-II worker")
    parser.add_argument("--event", help="Inline JSON event payload or path to a JSON file")
    parser.add_argument("--payload", help="Inline JSON job payload or path to a JSON file")
    parser.add_argument("--request-id", help="Explicit request identifier when payload is raw schedule data")
    args = parser.parse_args(argv)

    for candidate in (args.event, args.payload):
        loaded = _load_json_from_cli_or_env(candidate)
        if loaded is not None:
            return loaded, args.request_id

    for env_name in PAYLOAD_ENV_NAMES:
        raw_value = os.getenv(env_name)
        if raw_value:
            try:
                loaded = _load_json_from_cli_or_env(raw_value)
            except Exception as exc:
                logger.warning(
                    "Ignoring malformed worker payload from %s; trying next source: %s",
                    env_name,
                    exc,
                )
                continue

            if loaded is not None:
                return loaded, args.request_id

    raise RuntimeError(
        "Missing worker event payload. Provide --event/--payload or one of the "
        f"environment variables: {', '.join(PAYLOAD_ENV_NAMES)}"
    )


def _extract_request_id(event: dict[str, Any], cli_request_id: str | None = None) -> str:
    if cli_request_id:
        return cli_request_id.strip()

    for key in ("request_id", "requestId", "RequestId"):
        value = event.get(key)
        if value:
            return str(value).strip()

    for env_name in REQUEST_ID_ENV_NAMES:
        value = os.getenv(env_name, "").strip()
        if value:
            return value

    raise RuntimeError("Missing request_id. Provide it in the event or via REQUEST_ID/--request-id")


def _unwrap_event(event: Any) -> Any:
    if isinstance(event, list) and event:
        return _unwrap_event(event[0])

    if not isinstance(event, dict):
        return event

    if "detail" in event:
        return _unwrap_event(event["detail"])

    if "body" in event:
        return _unwrap_event(_load_json_value(event["body"]))

    if "Body" in event:
        return _unwrap_event(_load_json_value(event["Body"]))

    if "Records" in event and isinstance(event["Records"], list) and event["Records"]:
        return _unwrap_event(event["Records"][0])

    return event


def _normalize_job(event: dict[str, Any], cli_request_id: str | None = None) -> WorkerJob:
    normalized_event = _unwrap_event(event)

    if isinstance(normalized_event, dict) and "payload" in normalized_event:
        request_id = _extract_request_id(normalized_event, cli_request_id)
        payload = normalized_event["payload"]
    else:
        request_id = _extract_request_id(normalized_event if isinstance(normalized_event, dict) else {}, cli_request_id)
        payload = normalized_event

    payload_data = _load_json_value(payload)
    if not isinstance(payload_data, dict):
        raise ValueError("Schedule payload must be a JSON object")

    return WorkerJob(request_id=request_id, payload=payload_data)


def _build_progress_callback(request_id: str, progress_update_interval: int):
    last_progress = 10

    def on_progress(generation: int, total_generations: int) -> None:
        nonlocal last_progress

        is_final_generation = generation >= total_generations
        should_emit_update = is_final_generation or generation % progress_update_interval == 0
        if not should_emit_update:
            return

        progress = 100 if is_final_generation else min(99, 10 + int((generation / max(total_generations, 1)) * 89))
        if progress <= last_progress:
            return

        last_progress = progress
        mark_running(
            request_id,
            progress_percent=progress,
            message=f"Schedule generation is running (generation {generation}/{total_generations})",
        )

    return on_progress


def _process_job(job: WorkerJob, progress_update_interval: int) -> None:
    logger.info("Starting job %s", job.request_id)
    schedule_request = ScheduleRunRequestDTO.model_validate(job.payload)
    mark_running(job.request_id, progress_percent=10, message="Schedule generation is running")

    result = GenerateScheduleUseCase().execute(
        schedule_request,
        progress_callback=_build_progress_callback(job.request_id, progress_update_interval),
    )
    mark_completed(job.request_id, result.model_dump(mode="json"))
    logger.info("Completed job %s", job.request_id)


def main(argv: list[str] | None = None) -> None:
    _configure_logging()

    job_request_id: str | None = None
    try:
        _configure_runtime_timeout()
        settings = get_settings()
        job_source, cli_request_id = _load_job_source(argv)
        try:
            job_request_id = _extract_request_id(job_source, cli_request_id)
        except Exception:
            job_request_id = None
        job = _normalize_job(job_source, cli_request_id=cli_request_id)
        job_request_id = job.request_id
        _process_job(job, settings.progress_update_interval)
        _clear_runtime_timeout()
        sys.exit(0)
    except Exception as exc:
        logger.exception("Worker task failed")

        if job_request_id:
            try:
                mark_failed(job_request_id, "Worker task failed")
            except Exception:
                logger.exception("Unable to persist failure state for %s", job_request_id)

        sys.exit(1)


if __name__ == "__main__":
    main()
