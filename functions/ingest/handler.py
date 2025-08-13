"""
Ingest Lambda function - validates payload and publishes to SQS
"""

import json
import os
import sys
import boto3
from botocore.exceptions import ClientError

# Add common utilities to path
sys.path.append("/opt/python")
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "common"))

from utils import (
    setup_logger,
    validate_event_payload,
    generate_idempotency_key,
    get_failure_mode,
    should_simulate_failure,
    create_sqs_message_attributes,
    put_eventbridge_event,
    get_current_timestamp,
    parse_api_gateway_event,
    create_api_response,
    log_structured,
)

# Initialize logger
logger = setup_logger(__name__)

# Initialize AWS clients
sqs = boto3.client("sqs")

# Environment variables
QUEUE_URL = os.environ["QUEUE_URL"]
EVENT_BUS_NAME = os.environ["EVENT_BUS_NAME"]
ENV_NAME = os.environ["ENV_NAME"]


def lambda_handler(event, context):
    """
    Main Lambda handler for ingestion
    """
    request_id = context.aws_request_id

    try:
        # Parse the incoming event
        method, body, query_params = parse_api_gateway_event(event)

        # Handle health check
        if event.get("rawPath") == "/health":
            return handle_health_check(request_id)

        # Only accept POST requests for /events
        if method != "POST":
            log_structured(
                logger, "WARN", "Method not allowed", request_id, method=method
            )
            return create_api_response(405, {"error": "Method not allowed"})

        # Validate payload
        is_valid, error_message = validate_event_payload(body)
        if not is_valid:
            log_structured(
                logger,
                "ERROR",
                "Validation failed",
                request_id,
                error=error_message,
                payload=body,
            )
            return create_api_response(400, {"error": error_message})

        # Get failure mode for testing
        failure_mode = get_failure_mode()

        # Check if we should simulate failure
        should_fail, error_type = should_simulate_failure(failure_mode, request_id)
        if should_fail and error_type == "SchemaValidationError":
            log_structured(
                logger,
                "ERROR",
                "Simulated validation failure",
                request_id,
                failureMode=failure_mode,
                errorType=error_type,
            )
            return create_api_response(
                400, {"error": "Simulated schema validation error"}
            )

        # Generate or extract idempotency key
        if "idempotencyKey" in body:
            idempotency_key = body["idempotencyKey"]
            log_structured(
                logger,
                "INFO",
                "Using provided idempotency key",
                request_id,
                idempotencyKey=idempotency_key,
            )
        else:
            idempotency_key = generate_idempotency_key(body)
            log_structured(
                logger,
                "INFO",
                "Generated idempotency key",
                request_id,
                idempotencyKey=idempotency_key,
            )

        # Add metadata to payload
        enriched_payload = {
            **body,
            "idempotencyKey": idempotency_key,
            "ingestedAt": get_current_timestamp(),
            "requestId": request_id,
        }

        # Create SQS message attributes
        message_attributes = create_sqs_message_attributes(
            idempotency_key=idempotency_key,
            error_type_candidate=error_type if should_fail else "none",
        )

        # Send message to SQS
        try:
            response = sqs.send_message(
                QueueUrl=QUEUE_URL,
                MessageBody=json.dumps(enriched_payload),
                MessageAttributes=message_attributes,
            )

            message_id = response["MessageId"]

            log_structured(
                logger,
                "INFO",
                "Message sent to SQS",
                request_id,
                messageId=message_id,
                idempotencyKey=idempotency_key,
                queueUrl=QUEUE_URL,
            )

            # Emit success event to EventBridge
            event_detail = {
                "eventId": message_id,
                "idempotencyKey": idempotency_key,
                "status": "INGESTED",
                "requestId": request_id,
                "ingestedAt": get_current_timestamp(),
            }

            put_eventbridge_event(
                event_bus_name=EVENT_BUS_NAME,
                source="ingestion.pipeline",
                detail_type="Ingestion Received",
                detail=event_detail,
            )

            # Return success response
            return create_api_response(
                202,
                {
                    "message": "Event accepted for processing",
                    "messageId": message_id,
                    "idempotencyKey": idempotency_key,
                },
            )

        except ClientError as e:
            error_code = e.response["Error"]["Code"]
            error_message = e.response["Error"]["Message"]

            log_structured(
                logger,
                "ERROR",
                "Failed to send message to SQS",
                request_id,
                errorCode=error_code,
                errorMessage=error_message,
                idempotencyKey=idempotency_key,
            )

            return create_api_response(
                500,
                {
                    "error": "Failed to process event",
                    "details": "Internal server error",
                },
            )

    except Exception as e:
        log_structured(
            logger,
            "ERROR",
            "Unexpected error in ingest handler",
            request_id,
            error=str(e),
            errorType=type(e).__name__,
        )

        return create_api_response(500, {"error": "Internal server error"})


def handle_health_check(request_id: str):
    """
    Handle health check endpoint
    """
    try:
        # Simple health check - verify SQS queue is accessible
        sqs.get_queue_attributes(QueueUrl=QUEUE_URL, AttributeNames=["QueueArn"])

        log_structured(
            logger, "INFO", "Health check passed", request_id, status="healthy"
        )

        return create_api_response(
            200,
            {
                "status": "healthy",
                "service": "ingestion-api",
                "environment": ENV_NAME,
                "timestamp": get_current_timestamp(),
            },
        )

    except Exception as e:
        log_structured(logger, "ERROR", "Health check failed", request_id, error=str(e))

        return create_api_response(
            503, {"status": "unhealthy", "error": "Service dependencies unavailable"}
        )
