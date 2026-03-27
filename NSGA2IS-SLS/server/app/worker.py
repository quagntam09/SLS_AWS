from __future__ import annotations

import json
import logging
import os
import signal
import time
import traceback
from threading import Event

import boto3

from .application.services.async_schedule_service import mark_completed, mark_failed, mark_running
from .application.use_cases.generate_schedule import GenerateScheduleUseCase
from .config import get_settings
from .domain.schemas import ScheduleRunRequestDTO


QUEUE_URL_ENV = "QUEUE_URL"
AWS_REGION_ENV = "AWS_REGION"
RECEIVE_WAIT_SECONDS = 20
MESSAGE_VISIBILITY_TIMEOUT_SECONDS = 1800
ERROR_SLEEP_SECONDS = 5

_stop_event = Event()
logger = logging.getLogger(__name__)


def _required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def _queue_client():
    region_name = os.environ.get(AWS_REGION_ENV, "ap-southeast-1")
    return boto3.client("sqs", region_name=region_name)


def _install_signal_handlers() -> None:
    def _handle_stop_signal(_signum, _frame) -> None:
        _stop_event.set()

    signal.signal(signal.SIGTERM, _handle_stop_signal)
    signal.signal(signal.SIGINT, _handle_stop_signal)


def _build_progress_callback(request_id: str, progress_update_interval: int):
    last_progress = 10

    def on_progress(generation: int, total_generations: int) -> None:
        nonlocal last_progress
        is_final_generation = generation >= total_generations
        should_emit_update = is_final_generation or generation % progress_update_interval == 0
        if not should_emit_update:
            return

        progress = 100 if is_final_generation else min(
            99,
            10 + int((generation / max(total_generations, 1)) * 89),
        )
        if progress <= last_progress:
            return

        last_progress = progress
        mark_running(
            request_id,
            progress_percent=progress,
            message=f"Schedule generation is running (generation {generation}/{total_generations})",
        )

    return on_progress


def _process_message(message: dict[str, object], progress_update_interval: int) -> None:
    request_id = ""
    try:
        body = json.loads(str(message["Body"]))
        request_id = str(body["request_id"])
        payload = body["payload"]

        schedule_request = ScheduleRunRequestDTO.model_validate(payload)
        mark_running(request_id, progress_percent=10, message="Schedule generation is running")

        print(f"\nĐÃ BẮT ĐƯỢC JOB! Đang xử lý Request ID: {request_id}")
        result = GenerateScheduleUseCase().execute(
            schedule_request,
            progress_callback=_build_progress_callback(request_id, progress_update_interval),
        )
        mark_completed(request_id, result.model_dump(mode="json"))
        print(f"xử lý thành công Request ID: {request_id}")
    except Exception:
        if request_id:
            mark_failed(request_id, traceback.format_exc())
        raise


def run_worker() -> None:
    queue_url = _required_env(QUEUE_URL_ENV)

    settings = get_settings()
    progress_update_interval = settings.progress_update_interval
    sqs_client = _queue_client()

    print(f"Bắt đầu lắng nghe tại Queue: {queue_url}")

    while not _stop_event.is_set():
        logger.info("[worker] Polling for new messages...")
        try:
            response = sqs_client.receive_message(
                QueueUrl=queue_url,
                MaxNumberOfMessages=1,
                WaitTimeSeconds=RECEIVE_WAIT_SECONDS,
                VisibilityTimeout=MESSAGE_VISIBILITY_TIMEOUT_SECONDS,
                AttributeNames=["All"],
                MessageAttributeNames=["All"],
            )
            messages = response.get("Messages", [])
            if not messages:
                continue

            for message in messages:
                try:
                    _process_message(message, progress_update_interval)
                    sqs_client.delete_message(
                        QueueUrl=queue_url,
                        ReceiptHandle=str(message["ReceiptHandle"]),
                    )
                except Exception:
                    traceback.print_exc()
                    logger.exception("[worker] Failed to process message")
                    if not _stop_event.is_set():
                        time.sleep(ERROR_SLEEP_SECONDS)
        except Exception:
            traceback.print_exc()
            logger.exception("[worker] Polling error")
            if not _stop_event.is_set():
                time.sleep(ERROR_SLEEP_SECONDS)


def main() -> int:
    try:
        logging.basicConfig(level=logging.INFO, format="%(message)s")
        _install_signal_handlers()
        print("[worker] Starting SQS long-polling worker")
        run_worker()
        print("[worker] Worker stopped normally")
        return 0
    except Exception as e:
        print(f"[worker] CRITICAL ERROR: {e}")
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
