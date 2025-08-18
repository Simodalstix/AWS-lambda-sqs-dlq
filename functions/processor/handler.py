"""
Processor Lambda function - handles business logic processing only
Separated from worker for single responsibility principle
"""

import json
import os
import sys
import time
import boto3
from botocore.exceptions import ClientError

# Add common utilities to path
sys.path.append("/opt/python")
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "common"))

from utils import (
    setup_logger,
    get_failure_mode,
    should_simulate_failure,
    get_current_timestamp,
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
    Main Lambda handler for business logic processing
    """
    request_id = context.aws_request_id

    log_structured(
        logger,
        "INFO",
        "Processing started",
        request_id,
        recordCount=len(event.get("processedRecords", [])),
    )

    # Process records that passed idempotency check
    processed_records = event.get("processedRecords", [])
    batch_item_failures = event.get("batchItemFailures", [])
    processing_results = []

    for record_info in processed_records:
        try:
            result = process_business_logic(record_info, request_id)
            processing_results.append(result)

            if not result["success"]:
                # Add to batch failures for retry
                batch_item_failures.append(
                    {"itemIdentifier": record_info["record"]["messageId"]}
                )

        except Exception as e:
            log_structured(
                logger,
                "ERROR",
                "Failed to process business logic",
                request_id,
                messageId=record_info["record"]["messageId"],
                error=str(e),
                errorType=type(e).__name__,
            )

            # Add to batch failures for retry
            batch_item_failures.append(
                {"itemIdentifier": record_info["record"]["messageId"]}
            )

    # Return results for event publishing
    response = {
        "batchItemFailures": batch_item_failures,
        "processingResults": processing_results,
        "totalRecords": len(processed_records),
        "failedRecords": len(
            [r for r in processing_results if not r.get("success", False)]
        ),
        "successfulRecords": len(
            [r for r in processing_results if r.get("success", False)]
        ),
    }

    log_structured(
        logger,
        "INFO",
        "Processing completed",
        request_id,
        totalRecords=len(processed_records),
        failedRecords=response["failedRecords"],
        successfulRecords=response["successfulRecords"],
    )

    return response


def process_business_logic(record_info: dict, request_id: str) -> dict:
    """
    Process business logic for a single message
    Returns dict with success status and results
    """
    record = record_info["record"]
    idempotency_key = record_info["idempotencyKey"]
    message_id = record["messageId"]

    try:
        # Parse message body
        body = json.loads(record["body"])

        log_structured(
            logger,
            "INFO",
            "Processing business logic",
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

                # Update status to FAILED in DynamoDB
                update_processing_status(
                    idempotency_key, "FAILED", error="Simulated transient error"
                )

                return {
                    "success": False,
                    "idempotencyKey": idempotency_key,
                    "messageId": message_id,
                    "error": "Simulated transient error",
                    "errorType": error_type,
                }

        # Simulate actual business logic processing
        start_time = time.time()
        processing_result = simulate_business_logic(body, request_id)

        if processing_result["success"]:
            # Update status to SUCCEEDED in DynamoDB
            update_processing_status(
                idempotency_key, "SUCCEEDED", result=processing_result["result"]
            )

            log_structured(
                logger,
                "INFO",
                "Business logic processed successfully",
                request_id,
                idempotencyKey=idempotency_key,
                messageId=message_id,
                durationMs=int((time.time() - start_time) * 1000),
            )

            return {
                "success": True,
                "idempotencyKey": idempotency_key,
                "messageId": message_id,
                "result": processing_result["result"],
                "payload": body,
                "durationMs": int((time.time() - start_time) * 1000),
            }

        else:
            # Update status to FAILED in DynamoDB
            update_processing_status(
                idempotency_key, "FAILED", error=processing_result["error"]
            )

            log_structured(
                logger,
                "ERROR",
                "Business logic processing failed",
                request_id,
                idempotencyKey=idempotency_key,
                messageId=message_id,
                error=processing_result["error"],
                errorType="ProcessingError",
            )

            return {
                "success": False,
                "idempotencyKey": idempotency_key,
                "messageId": message_id,
                "error": processing_result["error"],
                "errorType": "ProcessingError",
                "payload": body,
            }

    except Exception as e:
        # Update status to FAILED in DynamoDB
        update_processing_status(idempotency_key, "FAILED", error=str(e))

        log_structured(
            logger,
            "ERROR",
            "Unexpected error processing business logic",
            request_id,
            messageId=message_id,
            idempotencyKey=idempotency_key,
            error=str(e),
            errorType=type(e).__name__,
        )

        return {
            "success": False,
            "idempotencyKey": idempotency_key,
            "messageId": message_id,
            "error": str(e),
            "errorType": type(e).__name__,
        }


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
            "processedBy": "processor-lambda",
            "processedAt": get_current_timestamp(),
        }

        return {"success": True, "result": result}

    except Exception as e:
        return {"success": False, "error": f"Processing error: {str(e)}"}


def update_processing_status(
    idempotency_key: str, status: str, result: dict = None, error: str = None
):
    """
    Update processing status in DynamoDB
    """
    try:
        update_expression = "SET #status = :status"
        expression_attribute_names = {"#status": "status"}
        expression_attribute_values = {":status": status}

        if status == "SUCCEEDED" and result:
            update_expression += ", processedAt = :processedAt, result = :result"
            expression_attribute_values[":processedAt"] = get_current_timestamp()
            expression_attribute_values[":result"] = result
        elif status == "FAILED" and error:
            update_expression += ", failedAt = :failedAt, errorMessage = :error"
            expression_attribute_values[":failedAt"] = get_current_timestamp()
            expression_attribute_values[":error"] = error

        table.update_item(
            Key={"idempotencyKey": idempotency_key},
            UpdateExpression=update_expression,
            ExpressionAttributeNames=expression_attribute_names,
            ExpressionAttributeValues=expression_attribute_values,
        )
    except Exception as e:
        logger.error(f"Failed to update processing status: {str(e)}")
