import json
import os
import uuid
from datetime import datetime, timezone
from functools import lru_cache
from time import sleep
from typing import Any, Dict, Optional

import boto3
from botocore.exceptions import (
    BotoCoreError,
    ClientError,
    ConnectionClosedError,
    EndpointConnectionError,
    ReadTimeoutError,
)


MAX_RETRIES = 3
BASE_BACKOFF_SECONDS = 0.25
MAX_ERROR_LENGTH = 1000
RETRIABLE_ERROR_CODES = {
    "InternalError",
    "InternalFailure",
    "RequestTimeout",
    "RequestTimeoutException",
    "Throttling",
    "ThrottlingException",
    "TooManyRequestsException",
    "ProvisionedThroughputExceededException",
    "ServiceUnavailable",
    "SlowDown",
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


@lru_cache(maxsize=1)
def _table():
    table_name = _required_env("SCHEDULE_TABLE_NAME")
    dynamodb = boto3.resource("dynamodb")
    return dynamodb.Table(table_name)


@lru_cache(maxsize=1)
def _sqs_client():
    return boto3.client("sqs")


@lru_cache(maxsize=1)
def _s3_client():
    return boto3.client("s3")


def _queue_url() -> str:
    return _required_env("SCHEDULE_QUEUE_URL")


def _bucket_name() -> str:
    return _required_env("SCHEDULE_RESULTS_BUCKET")


def _truncate_error(error: str) -> str:
    if len(error) <= MAX_ERROR_LENGTH:
        return error
    return error[: MAX_ERROR_LENGTH - 3] + "..."


def _safe_error_message(exc: Exception) -> str:
    message = str(exc) or exc.__class__.__name__
    return _truncate_error(message)


def _is_retriable_client_error(exc: ClientError) -> bool:
    code = exc.response.get("Error", {}).get("Code", "")
    return code in RETRIABLE_ERROR_CODES


def _is_retriable_exception(exc: Exception) -> bool:
    if isinstance(exc, (EndpointConnectionError, ConnectionClosedError, ReadTimeoutError)):
        return True
    if isinstance(exc, ClientError):
        return _is_retriable_client_error(exc)
    return False


def _with_retries(operation_name: str, fn):
    last_exc: Optional[Exception] = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            return fn()
        except (ClientError, BotoCoreError) as exc:
            last_exc = exc
            if attempt >= MAX_RETRIES or not _is_retriable_exception(exc):
                break
            sleep(BASE_BACKOFF_SECONDS * (2 ** (attempt - 1)))

    assert last_exc is not None
    raise RuntimeError(f"{operation_name} failed: {_safe_error_message(last_exc)}") from last_exc


def _best_effort_mark_failed(request_id: str, error: str) -> None:
    try:
        _with_retries(
            "DynamoDB update_item (mark failed)",
            lambda: _table().update_item(
                Key={"request_id": request_id},
                UpdateExpression=(
                    "SET #s = :s, progress_percent = :p, #m = :m, #e = :e, updated_at = :u"
                ),
                ExpressionAttributeNames={"#s": "status", "#m": "message", "#e": "error"},
                ExpressionAttributeValues={
                    ":s": "failed",
                    ":p": 100,
                    ":m": "Schedule generation failed",
                    ":e": _truncate_error(error),
                    ":u": _utc_now(),
                },
            ),
        )
    except Exception as exc:
        print(
            f"[async_schedule_service] Unable to persist failed status for {request_id}: "
            f"{_safe_error_message(exc)}"
        )


def create_schedule_request(payload: Dict[str, Any]) -> Dict[str, Any]:
    request_id = f"req_{uuid.uuid4().hex[:12]}"
    now = _utc_now()

    item = {
        "request_id": request_id,
        "status": "queued",
        "progress_percent": 0,
        "message": "Request queued for processing",
        "created_at": now,
        "updated_at": now,
        "error": None,
        "result_s3_key": None,
    }
    _with_retries(
        "DynamoDB put_item",
        lambda: _table().put_item(
            Item=item,
            ConditionExpression="attribute_not_exists(request_id)",
        ),
    )

    try:
        _with_retries(
            "SQS send_message",
            lambda: _sqs_client().send_message(
                QueueUrl=_queue_url(),
                MessageBody=json.dumps(
                    {
                        "request_id": request_id,
                        "payload": payload,
                    }
                ),
            ),
        )
    except Exception as exc:
        _best_effort_mark_failed(request_id, f"Queue dispatch failed: {_safe_error_message(exc)}")
        raise

    return {
        "request_id": request_id,
        "status": "queued",
        "progress_percent": 0,
        "message": "Schedule generation request submitted",
    }


def mark_running(
    request_id: str,
    progress_percent: int = 10,
    message: str = "Schedule generation is running",
) -> None:
    _with_retries(
        "DynamoDB update_item (mark running)",
        lambda: _table().update_item(
            Key={"request_id": request_id},
            UpdateExpression="SET #s = :s, progress_percent = :p, #m = :m, updated_at = :u",
            ConditionExpression="attribute_exists(request_id)",
            ExpressionAttributeNames={"#s": "status", "#m": "message"},
            ExpressionAttributeValues={
                ":s": "running",
                ":p": progress_percent,
                ":m": message,
                ":u": _utc_now(),
            },
        ),
    )


def mark_completed(request_id: str, result: Dict[str, Any]) -> None:
    s3_key = f"results/{request_id}.json"
    _with_retries(
        "S3 put_object",
        lambda: _s3_client().put_object(
            Bucket=_bucket_name(),
            Key=s3_key,
            Body=json.dumps(result).encode("utf-8"),
            ContentType="application/json",
        ),
    )

    _with_retries(
        "DynamoDB update_item (mark completed)",
        lambda: _table().update_item(
            Key={"request_id": request_id},
            UpdateExpression=(
                "SET #s = :s, progress_percent = :p, #m = :m, "
                "result_s3_key = :k, updated_at = :u, #e = :e"
            ),
            ConditionExpression="attribute_exists(request_id)",
            ExpressionAttributeNames={"#s": "status", "#m": "message", "#e": "error"},
            ExpressionAttributeValues={
                ":s": "completed",
                ":p": 100,
                ":m": "Schedule generation completed successfully",
                ":k": s3_key,
                ":u": _utc_now(),
                ":e": None,
            },
        ),
    )


def mark_failed(request_id: str, error: str) -> None:
    _best_effort_mark_failed(request_id, error)


def get_schedule_progress(request_id: str) -> Optional[Dict[str, Any]]:
    response = _with_retries(
        "DynamoDB get_item",
        lambda: _table().get_item(Key={"request_id": request_id}),
    )
    item = response.get("Item")
    if not item:
        return None

    result = None
    result_error: Optional[str] = None
    if item.get("status") == "completed" and item.get("result_s3_key"):
        try:
            obj = _with_retries(
                "S3 get_object",
                lambda: _s3_client().get_object(
                    Bucket=_bucket_name(),
                    Key=item["result_s3_key"],
                ),
            )
            result = json.loads(obj["Body"].read().decode("utf-8"))
        except Exception as exc:
            result_error = f"Result payload unavailable: {_safe_error_message(exc)}"
            print(f"[async_schedule_service] {request_id}: {result_error}")

    existing_error = item.get("error")
    combined_error = existing_error
    if result_error:
        combined_error = f"{existing_error}; {result_error}" if existing_error else result_error
        combined_error = _truncate_error(combined_error)

    return {
        "request_id": item["request_id"],
        "status": item.get("status", "queued"),
        "progress_percent": float(item.get("progress_percent", 0)),
        "message": item.get("message", ""),
        "result": result,
        "error": combined_error,
    }
