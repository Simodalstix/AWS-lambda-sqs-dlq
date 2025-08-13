"""
Common utilities for Lambda functions in the ingestion pipeline
"""

import json
import hashlib
import time
import logging
import os
from datetime import datetime, timezone
from typing import Dict, Any, Optional, Union
import boto3
from botocore.exceptions import ClientError


# Configure structured logging
def setup_logger(name: str) -> logging.Logger:
    """Set up structured JSON logging"""
    logger = logging.getLogger(name)

    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            '{"timestamp": "%(asctime)s", "level": "%(levelname)s", '
            '"logger": "%(name)s", "message": "%(message)s"}'
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    log_level = os.environ.get("LOG_LEVEL", "INFO")
    logger.setLevel(getattr(logging, log_level))

    return logger


def generate_idempotency_key(payload: Dict[str, Any]) -> str:
    """
    Generate idempotency key from payload using SHA256 hash
    """
    # Create canonical representation of payload
    canonical_payload = json.dumps(payload, sort_keys=True, separators=(",", ":"))

    # Generate SHA256 hash
    hash_object = hashlib.sha256(canonical_payload.encode("utf-8"))
    return hash_object.hexdigest()


def validate_event_payload(payload: Dict[str, Any]) -> tuple[bool, Optional[str]]:
    """
    Validate incoming event payload
    Returns (is_valid, error_message)
    """
    required_fields = ["orderId", "amount"]

    # Check required fields
    for field in required_fields:
        if field not in payload:
            return False, f"Missing required field: {field}"

    # Validate orderId
    if not isinstance(payload["orderId"], str) or not payload["orderId"].strip():
        return False, "orderId must be a non-empty string"

    # Validate amount
    try:
        amount = float(payload["amount"])
        if amount <= 0:
            return False, "amount must be a positive number"
    except (ValueError, TypeError):
        return False, "amount must be a valid number"

    return True, None


def get_failure_mode() -> str:
    """
    Get current failure mode from SSM parameter
    """
    try:
        ssm = boto3.client("ssm")
        response = ssm.get_parameter(Name="/ingestion/failure_mode")
        return response["Parameter"]["Value"]
    except ClientError:
        return "none"


def should_simulate_failure(failure_mode: str, request_id: str) -> tuple[bool, str]:
    """
    Determine if we should simulate a failure based on failure mode
    Returns (should_fail, error_type)
    """
    if failure_mode == "none":
        return False, ""

    if failure_mode == "poison_payload":
        return True, "SchemaValidationError"

    if failure_mode == "slow_downstream":
        return True, "TimeoutError"

    if failure_mode == "random_fail_p30":
        # Use request_id hash to get deterministic randomness
        hash_val = int(hashlib.md5(request_id.encode()).hexdigest()[:8], 16)
        if hash_val % 100 < 30:  # 30% failure rate
            return True, "TransientError"

    return False, ""


def create_sqs_message_attributes(
    idempotency_key: str, error_type_candidate: str = "none"
) -> Dict[str, Dict[str, str]]:
    """
    Create SQS message attributes for tracking
    """
    return {
        "idempotencyKey": {"StringValue": idempotency_key, "DataType": "String"},
        "submittedAt": {
            "StringValue": datetime.now(timezone.utc).isoformat(),
            "DataType": "String",
        },
        "errorTypeCandidate": {
            "StringValue": error_type_candidate,
            "DataType": "String",
        },
    }


def put_eventbridge_event(
    event_bus_name: str, source: str, detail_type: str, detail: Dict[str, Any]
) -> bool:
    """
    Put event to EventBridge custom bus
    """
    try:
        eventbridge = boto3.client("events")

        response = eventbridge.put_events(
            Entries=[
                {
                    "Source": source,
                    "DetailType": detail_type,
                    "Detail": json.dumps(detail),
                    "EventBusName": event_bus_name,
                }
            ]
        )

        # Check for failures
        if response.get("FailedEntryCount", 0) > 0:
            return False

        return True
    except Exception:
        return False


def get_current_timestamp() -> str:
    """Get current timestamp in ISO format"""
    return datetime.now(timezone.utc).isoformat()


def calculate_ttl_timestamp(days: int = 7) -> int:
    """Calculate TTL timestamp for DynamoDB (Unix timestamp)"""
    return int(time.time()) + (days * 24 * 60 * 60)


def extract_sqs_records(event: Dict[str, Any]) -> list:
    """Extract SQS records from Lambda event"""
    return event.get("Records", [])


def create_batch_item_failure(message_id: str) -> Dict[str, str]:
    """Create batch item failure for partial batch response"""
    return {"itemIdentifier": message_id}


def parse_api_gateway_event(
    event: Dict[str, Any],
) -> tuple[str, Dict[str, Any], Dict[str, str]]:
    """
    Parse API Gateway event and extract method, body, and query parameters
    """
    method = event.get("requestContext", {}).get("http", {}).get("method", "GET")

    # Parse body
    body = {}
    if event.get("body"):
        try:
            body = json.loads(event["body"])
        except json.JSONDecodeError:
            body = {}

    # Parse query parameters
    query_params = event.get("queryStringParameters") or {}

    return method, body, query_params


def create_api_response(
    status_code: int,
    body: Union[Dict[str, Any], str],
    headers: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """
    Create API Gateway response
    """
    default_headers = {
        "Content-Type": "application/json",
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Headers": "Content-Type,Authorization",
        "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
    }

    if headers:
        default_headers.update(headers)

    response_body = body if isinstance(body, str) else json.dumps(body)

    return {
        "statusCode": status_code,
        "headers": default_headers,
        "body": response_body,
    }


def log_structured(
    logger: logging.Logger, level: str, message: str, request_id: str, **kwargs
) -> None:
    """
    Log structured message with additional context
    """
    log_data = {"message": message, "requestId": request_id, **kwargs}

    # Convert to JSON string for structured logging
    log_message = json.dumps(log_data)

    getattr(logger, level.lower())(log_message)
