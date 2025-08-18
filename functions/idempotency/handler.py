"""
Idempotency Lambda function - handles idempotency checks only
Separated from worker for single responsibility principle
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

# Environment variables
IDEMPOTENCY_TABLE = os.environ["IDEMPOTENCY_TABLE"]
ENV_NAME = os.environ["ENV_NAME"]

# Get DynamoDB table
table = dynamodb.Table(IDEMPOTENCY_TABLE)


def lambda_handler(event, context):
    """
    Main Lambda handler for idempotency checks
    """
    request_id = context.aws_request_id

    log_structured(
        logger,
        "INFO",
        "Idempotency check started",
        request_id,
        recordCount=len(event.get("Records", [])),
    )

    # Extract SQS records
    records = extract_sqs_records(event)
    batch_item_failures = []
    processed_records = []

    for record in records:
        try:
            result = check_idempotency(record, request_id)
            if result["should_process"]:
                processed_records.append(
                    {
                        "record": record,
                        "idempotencyKey": result["idempotency_key"],
                        "status": result["status"],
                    }
                )
            elif result["status"] == "FAILED":
                # Add to batch failures for retry
                batch_item_failures.append(
                    create_batch_item_failure(record["messageId"])
                )
        except Exception as e:
            log_structured(
                logger,
                "ERROR",
                "Failed to check idempotency",
                request_id,
                messageId=record["messageId"],
                error=str(e),
                errorType=type(e).__name__,
            )

            # Add to batch failures for retry
            batch_item_failures.append(create_batch_item_failure(record["messageId"]))

    # Return results for downstream processing
    response = {
        "batchItemFailures": batch_item_failures,
        "processedRecords": processed_records,
        "totalRecords": len(records),
        "failedRecords": len(batch_item_failures),
        "successfulRecords": len(processed_records),
    }

    log_structured(
        logger,
        "INFO",
        "Idempotency check completed",
        request_id,
        totalRecords=len(records),
        failedRecords=len(batch_item_failures),
        successfulRecords=len(processed_records),
    )

    return response


def check_idempotency(record: dict, request_id: str) -> dict:
    """
    Check idempotency for a single message
    Returns dict with should_process, idempotency_key, and status
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
            return {
                "should_process": False,
                "idempotency_key": None,
                "status": "FAILED",
                "error": "Missing idempotency key",
            }

        log_structured(
            logger,
            "INFO",
            "Checking idempotency",
            request_id,
            messageId=message_id,
            idempotencyKey=idempotency_key,
        )

        # Check idempotency in DynamoDB
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
                "New message - should process",
                request_id,
                idempotencyKey=idempotency_key,
                messageId=message_id,
            )

            return {
                "should_process": True,
                "idempotency_key": idempotency_key,
                "status": "NEW",
            }

        except ClientError as e:
            if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
                # Item already exists - check status
                existing_item = table.get_item(Key={"idempotencyKey": idempotency_key})[
                    "Item"
                ]

                existing_status = existing_item.get("status")

                log_structured(
                    logger,
                    "INFO",
                    "Idempotent message found",
                    request_id,
                    idempotencyKey=idempotency_key,
                    messageId=message_id,
                    existingStatus=existing_status,
                    idempotent="true",
                )

                # If already succeeded, don't process again
                if existing_status == "SUCCEEDED":
                    return {
                        "should_process": False,
                        "idempotency_key": idempotency_key,
                        "status": "SUCCEEDED",
                    }

                # If failed, we can retry - update attempts counter
                if existing_status == "FAILED":
                    table.update_item(
                        Key={"idempotencyKey": idempotency_key},
                        UpdateExpression="SET attempts = attempts + :inc, #status = :status",
                        ExpressionAttributeNames={"#status": "status"},
                        ExpressionAttributeValues={":inc": 1, ":status": "INFLIGHT"},
                    )

                    return {
                        "should_process": True,
                        "idempotency_key": idempotency_key,
                        "status": "RETRY",
                    }

                # If in flight, don't process (likely duplicate)
                return {
                    "should_process": False,
                    "idempotency_key": idempotency_key,
                    "status": "INFLIGHT",
                }

            else:
                raise e

    except Exception as e:
        log_structured(
            logger,
            "ERROR",
            "Unexpected error checking idempotency",
            request_id,
            messageId=message_id,
            error=str(e),
            errorType=type(e).__name__,
        )
        return {
            "should_process": False,
            "idempotency_key": (
                idempotency_key if "idempotency_key" in locals() else None
            ),
            "status": "FAILED",
            "error": str(e),
        }


def calculate_checksum(payload: dict) -> str:
    """
    Calculate checksum of payload for integrity verification
    """
    import hashlib

    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]
