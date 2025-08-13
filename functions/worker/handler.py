"""
Worker Lambda function - processes SQS messages with idempotency and partial batch response
"""

import json
import os
import sys
import time
import boto3
from botocore.exceptions import ClientError
from boto3.dynamodb.conditions import Attr

# Add common utilities to path
sys.path.append("/opt/python")
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "common"))

from utils import (
    setup_logger,
    get_failure_mode,
    should_simulate_failure,
    put_eventbridge_event,
    get_current_timestamp,
    calculate_ttl_timestamp,
    extract_sqs_records,
    create_batch_item_failure,
    log_structured,
)

# Initialize logger
logger = setup_logger(__name__)

# Initialize AWS clients
dynamodb = boto3.resource("dynamodb")
eventbridge = boto3.client("events")

# Environment variables
IDEMPOTENCY_TABLE = os.environ["IDEMPOTENCY_TABLE"]
EVENT_BUS_NAME = os.environ["EVENT_BUS_NAME"]
ENV_NAME = os.environ["ENV_NAME"]

# Get DynamoDB table
table = dynamodb.Table(IDEMPOTENCY_TABLE)


def lambda_handler(event, context):
    """
    Main Lambda handler for worker processing
    """
    request_id = context.aws_request_id

    log_structured(
        logger,
        "INFO",
        "Worker processing started",
        request_id,
        recordCount=len(event.get("Records", [])),
    )

    # Extract SQS records
    records = extract_sqs_records(event)
    batch_item_failures = []

    for record in records:
        try:
            success = process_single_message(record, request_id)
            if not success:
                # Add to batch failures for retry
                batch_item_failures.append(
                    create_batch_item_failure(record["messageId"])
                )
        except Exception as e:
            log_structured(
                logger,
                "ERROR",
                "Failed to process message",
                request_id,
                messageId=record["messageId"],
                error=str(e),
                errorType=type(e).__name__,
            )

            # Add to batch failures for retry
            batch_item_failures.append(create_batch_item_failure(record["messageId"]))

    # Return partial batch response
    response = {"batchItemFailures": batch_item_failures}

    log_structured(
        logger,
        "INFO",
        "Worker processing completed",
        request_id,
        totalRecords=len(records),
        failedRecords=len(batch_item_failures),
        successfulRecords=len(records) - len(batch_item_failures),
    )

    return response


def process_single_message(record: dict, request_id: str) -> bool:
    """
    Process a single SQS message with idempotency
    Returns True if successful, False if should retry
    """
    message_id = record["messageId"]

    try:
        # Parse message body
        body = json.loads(record["body"])
        idempotency_key = body.get("idempotencyKey")

        if not idempotency_key:
            log_structured(
                logger,
                "ERROR",
                "Missing idempotency key",
                request_id,
                messageId=message_id,
            )
            return False

        log_structured(
            logger,
            "INFO",
            "Processing message",
            request_id,
            messageId=message_id,
            idempotencyKey=idempotency_key,
        )

        # Get failure mode for testing
        failure_mode = get_failure_mode()

        # Check for simulated failures
        should_fail, error_type = should_simulate_failure(failure_mode, request_id)

        if should_fail:
            if error_type == "TimeoutError":
                # Simulate slow downstream by sleeping longer than function timeout
                log_structured(
                    logger,
                    "WARN",
                    "Simulating slow downstream",
                    request_id,
                    idempotencyKey=idempotency_key,
                    failureMode=failure_mode,
                )
                time.sleep(35)  # This will cause timeout

            elif error_type == "TransientError":
                log_structured(
                    logger,
                    "ERROR",
                    "Simulated transient error",
                    request_id,
                    idempotencyKey=idempotency_key,
                    errorType=error_type,
                )
                return False  # Will be retried

        # Check idempotency in DynamoDB
        start_time = time.time()

        try:
            # Try to create new record with condition that it doesn't exist
            table.put_item(
                Item={
                    "idempotencyKey": idempotency_key,
                    "status": "INFLIGHT",
                    "checksum": calculate_checksum(body),
                    "firstSeenAt": get_current_timestamp(),
                    "attempts": 1,
                    "expiresAt": calculate_ttl_timestamp(),
                    "requestId": request_id,
                    "messageId": message_id,
                },
                ConditionExpression=Attr("idempotencyKey").not_exists(),
            )

            log_structured(
                logger,
                "INFO",
                "New message - processing",
                request_id,
                idempotencyKey=idempotency_key,
                messageId=message_id,
            )

        except ClientError as e:
            if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
                # Item already exists - this is idempotent
                existing_item = table.get_item(Key={"idempotencyKey": idempotency_key})[
                    "Item"
                ]

                log_structured(
                    logger,
                    "INFO",
                    "Idempotent message",
                    request_id,
                    idempotencyKey=idempotency_key,
                    messageId=message_id,
                    existingStatus=existing_item.get("status"),
                    idempotent="true",
                )

                # If already succeeded, emit success event and return
                if existing_item.get("status") == "SUCCEEDED":
                    emit_success_event(idempotency_key, body, request_id, start_time)
                    return True

                # If failed, we can retry
                if existing_item.get("status") == "FAILED":
                    # Update attempts counter
                    table.update_item(
                        Key={"idempotencyKey": idempotency_key},
                        UpdateExpression="SET attempts = attempts + :inc, #status = :status",
                        ExpressionAttributeNames={"#status": "status"},
                        ExpressionAttributeValues={":inc": 1, ":status": "INFLIGHT"},
                    )

            else:
                raise e

        # Simulate business logic processing
        processing_result = simulate_business_logic(body, request_id)

        if processing_result["success"]:
            # Update status to SUCCEEDED
            table.update_item(
                Key={"idempotencyKey": idempotency_key},
                UpdateExpression="SET #status = :status, processedAt = :processedAt, result = :result",
                ExpressionAttributeNames={"#status": "status"},
                ExpressionAttributeValues={
                    ":status": "SUCCEEDED",
                    ":processedAt": get_current_timestamp(),
                    ":result": processing_result["result"],
                },
            )

            log_structured(
                logger,
                "INFO",
                "Message processed",
                request_id,
                idempotencyKey=idempotency_key,
                messageId=message_id,
                processed="true",
                durationMs=int((time.time() - start_time) * 1000),
            )

            # Emit success event
            emit_success_event(idempotency_key, body, request_id, start_time)
            return True

        else:
            # Update status to FAILED
            table.update_item(
                Key={"idempotencyKey": idempotency_key},
                UpdateExpression="SET #status = :status, failedAt = :failedAt, errorMessage = :error",
                ExpressionAttributeNames={"#status": "status"},
                ExpressionAttributeValues={
                    ":status": "FAILED",
                    ":failedAt": get_current_timestamp(),
                    ":error": processing_result["error"],
                },
            )

            log_structured(
                logger,
                "ERROR",
                "Message processing failed",
                request_id,
                idempotencyKey=idempotency_key,
                messageId=message_id,
                error=processing_result["error"],
                errorType="ProcessingError",
            )

            # Emit failure event
            emit_failure_event(
                idempotency_key, body, request_id, processing_result["error"]
            )
            return False

    except Exception as e:
        log_structured(
            logger,
            "ERROR",
            "Unexpected error processing message",
            request_id,
            messageId=message_id,
            error=str(e),
            errorType=type(e).__name__,
        )
        return False


def simulate_business_logic(payload: dict, request_id: str) -> dict:
    """
    Simulate business logic processing
    """
    try:
        # Simulate some processing time
        time.sleep(0.1)

        # Extract order details
        order_id = payload.get("orderId")
        amount = float(payload.get("amount", 0))

        # Simulate business rules
        if amount > 10000:
            return {"success": False, "error": "Amount exceeds maximum limit"}

        # Simulate successful processing
        result = {
            "orderId": order_id,
            "processedAmount": amount,
            "tax": round(amount * 0.1, 2),
            "total": round(amount * 1.1, 2),
            "processedBy": "worker-lambda",
            "processedAt": get_current_timestamp(),
        }

        return {"success": True, "result": result}

    except Exception as e:
        return {"success": False, "error": f"Processing error: {str(e)}"}


def calculate_checksum(payload: dict) -> str:
    """
    Calculate checksum of payload for integrity verification
    """
    import hashlib

    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]


def emit_success_event(
    idempotency_key: str, payload: dict, request_id: str, start_time: float
):
    """
    Emit success event to EventBridge
    """
    event_detail = {
        "eventId": f"success-{idempotency_key}",
        "idempotencyKey": idempotency_key,
        "status": "SUCCEEDED",
        "orderId": payload.get("orderId"),
        "amount": payload.get("amount"),
        "processedAt": get_current_timestamp(),
        "requestId": request_id,
        "durationMs": int((time.time() - start_time) * 1000),
    }

    put_eventbridge_event(
        event_bus_name=EVENT_BUS_NAME,
        source="ingestion.pipeline",
        detail_type="Ingestion Success",
        detail=event_detail,
    )


def emit_failure_event(
    idempotency_key: str, payload: dict, request_id: str, error_message: str
):
    """
    Emit failure event to EventBridge
    """
    event_detail = {
        "eventId": f"failure-{idempotency_key}",
        "idempotencyKey": idempotency_key,
        "status": "FAILED",
        "orderId": payload.get("orderId"),
        "amount": payload.get("amount"),
        "errorType": "ProcessingError",
        "errorMessage": error_message,
        "failedAt": get_current_timestamp(),
        "requestId": request_id,
    }

    put_eventbridge_event(
        event_bus_name=EVENT_BUS_NAME,
        source="ingestion.pipeline",
        detail_type="Ingestion Failure",
        detail=event_detail,
    )
