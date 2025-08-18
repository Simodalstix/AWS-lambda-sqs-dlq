"""
Redrive Lambda function - manages DLQ message redrive with safety controls
Enhanced with exponential backoff and error categorization
"""

import json
import os
import sys
import time
import random
import boto3
from botocore.exceptions import ClientError
from datetime import datetime, timezone

# Add common utilities to path
sys.path.append("/opt/python")
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "common"))

from utils import (
    setup_logger,
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
DLQ_URL = os.environ["DLQ_URL"]
ENV_NAME = os.environ["ENV_NAME"]

# Error categorization for better DLQ analysis
ERROR_TYPES = {
    "VALIDATION": "Schema or business rule violation",
    "TRANSIENT": "Temporary failure, retry possible",
    "PERMANENT": "Permanent failure, manual intervention needed",
    "TIMEOUT": "Processing timeout, increase resources",
    "PROCESSING": "Business logic processing error",
    "UNKNOWN": "Unclassified error type",
}


def lambda_handler(event, context):
    """
    Main Lambda handler for redrive operations
    """
    request_id = context.aws_request_id

    try:
        # Parse the incoming event
        method, body, query_params = parse_api_gateway_event(event)
        path = event.get("rawPath", "")

        log_structured(
            logger,
            "INFO",
            "Redrive operation started",
            request_id,
            method=method,
            path=path,
        )

        if path == "/redrive/preview":
            return handle_preview(query_params, request_id)
        elif path == "/redrive/start":
            return handle_start(body, request_id)
        elif path == "/redrive/cancel":
            return handle_cancel(body, request_id)
        else:
            return create_api_response(404, {"error": "Endpoint not found"})

    except Exception as e:
        log_structured(
            logger,
            "ERROR",
            "Unexpected error in redrive handler",
            request_id,
            error=str(e),
            errorType=type(e).__name__,
        )

        return create_api_response(500, {"error": "Internal server error"})


def handle_preview(query_params: dict, request_id: str):
    """
    Preview messages in DLQ without moving them
    """
    try:
        # Parse query parameters
        max_messages = min(int(query_params.get("maxMessages", 20)), 100)
        error_type_filter = query_params.get("errorType", "")
        min_age_seconds = int(query_params.get("minAgeSeconds", 0))

        log_structured(
            logger,
            "INFO",
            "Previewing DLQ messages",
            request_id,
            maxMessages=max_messages,
            errorTypeFilter=error_type_filter,
            minAgeSeconds=min_age_seconds,
        )

        # Get DLQ attributes
        dlq_attributes = sqs.get_queue_attributes(
            QueueUrl=DLQ_URL,
            AttributeNames=[
                "ApproximateNumberOfMessages",
                "ApproximateNumberOfMessagesNotVisible",
            ],
        )

        total_messages = int(
            dlq_attributes["Attributes"].get("ApproximateNumberOfMessages", 0)
        )
        in_flight_messages = int(
            dlq_attributes["Attributes"].get("ApproximateNumberOfMessagesNotVisible", 0)
        )

        # Receive messages for preview
        messages = []
        received_count = 0

        while received_count < max_messages:
            batch_size = min(10, max_messages - received_count)

            response = sqs.receive_message(
                QueueUrl=DLQ_URL,
                MaxNumberOfMessages=batch_size,
                MessageAttributeNames=["All"],
                VisibilityTimeout=30,  # Short visibility timeout for preview
                WaitTimeSeconds=1,
            )

            batch_messages = response.get("Messages", [])
            if not batch_messages:
                break

            for message in batch_messages:
                # Check filters
                if should_include_message(message, error_type_filter, min_age_seconds):
                    preview = format_message_preview(message)
                    # Add error categorization to preview
                    preview["errorCategory"] = categorize_error_type(message)
                    preview["errorDescription"] = ERROR_TYPES.get(
                        preview["errorCategory"], "Unknown error type"
                    )
                    messages.append(preview)
                    received_count += 1

                # Return message to queue (make it visible again)
                sqs.change_message_visibility(
                    QueueUrl=DLQ_URL,
                    ReceiptHandle=message["ReceiptHandle"],
                    VisibilityTimeout=0,
                )

                if received_count >= max_messages:
                    break

        preview_data = {
            "dlqStats": {
                "totalMessages": total_messages,
                "inFlightMessages": in_flight_messages,
                "availableMessages": total_messages - in_flight_messages,
            },
            "previewMessages": messages,
            "filters": {
                "maxMessages": max_messages,
                "errorType": error_type_filter,
                "minAgeSeconds": min_age_seconds,
            },
            "timestamp": get_current_timestamp(),
        }

        log_structured(
            logger,
            "INFO",
            "DLQ preview completed",
            request_id,
            totalMessages=total_messages,
            previewedMessages=len(messages),
        )

        return create_api_response(200, preview_data)

    except Exception as e:
        log_structured(
            logger, "ERROR", "Failed to preview DLQ", request_id, error=str(e)
        )
        return create_api_response(500, {"error": "Failed to preview DLQ"})


def handle_start(body: dict, request_id: str):
    """
    Start redrive operation with safety controls
    """
    try:
        # Parse parameters
        max_messages = min(int(body.get("maxMessages", 100)), 1000)
        error_type_filter = body.get("errorType", "")
        min_age_seconds = int(body.get("minAgeSeconds", 300))  # Default 5 minutes
        per_message_delay_jitter = int(body.get("perMessageDelayJitter", 5))

        log_structured(
            logger,
            "INFO",
            "Starting redrive operation",
            request_id,
            maxMessages=max_messages,
            errorTypeFilter=error_type_filter,
            minAgeSeconds=min_age_seconds,
            delayJitter=per_message_delay_jitter,
        )

        # Safety check - ensure minimum age
        if min_age_seconds < 60:
            return create_api_response(
                400, {"error": "Minimum age must be at least 60 seconds for safety"}
            )

        # Get DLQ stats before redrive
        dlq_attributes = sqs.get_queue_attributes(
            QueueUrl=DLQ_URL, AttributeNames=["ApproximateNumberOfMessages"]
        )

        initial_dlq_count = int(
            dlq_attributes["Attributes"].get("ApproximateNumberOfMessages", 0)
        )

        if initial_dlq_count == 0:
            return create_api_response(
                200,
                {
                    "message": "No messages in DLQ to redrive",
                    "redriveStats": {
                        "initialDlqCount": 0,
                        "processedMessages": 0,
                        "redrivenMessages": 0,
                        "skippedMessages": 0,
                    },
                },
            )

        # Process messages in batches
        processed_count = 0
        redriven_count = 0
        skipped_count = 0

        while processed_count < max_messages:
            batch_size = min(10, max_messages - processed_count)

            response = sqs.receive_message(
                QueueUrl=DLQ_URL,
                MaxNumberOfMessages=batch_size,
                MessageAttributeNames=["All"],
                VisibilityTimeout=300,  # 5 minutes to process
                WaitTimeSeconds=2,
            )

            batch_messages = response.get("Messages", [])
            if not batch_messages:
                break

            for message in batch_messages:
                processed_count += 1

                try:
                    # Check if message should be redriven
                    if should_include_message(
                        message, error_type_filter, min_age_seconds
                    ):
                        # Calculate exponential backoff with jitter
                        receive_count = int(
                            message.get("Attributes", {}).get(
                                "ApproximateReceiveCount", 1
                            )
                        )
                        delay_seconds = calculate_exponential_backoff(
                            receive_count, per_message_delay_jitter
                        )

                        # Send message back to main queue
                        sqs.send_message(
                            QueueUrl=QUEUE_URL,
                            MessageBody=message["Body"],
                            MessageAttributes=message.get("MessageAttributes", {}),
                            DelaySeconds=min(delay_seconds, 900),  # Max 15 minutes
                        )

                        # Delete from DLQ
                        sqs.delete_message(
                            QueueUrl=DLQ_URL, ReceiptHandle=message["ReceiptHandle"]
                        )

                        redriven_count += 1

                        # Categorize error for logging
                        error_category = categorize_error_type(message)

                        log_structured(
                            logger,
                            "INFO",
                            "Message redriven",
                            request_id,
                            messageId=message["MessageId"],
                            delaySeconds=delay_seconds,
                            errorCategory=error_category,
                            receiveCount=receive_count,
                        )
                    else:
                        # Return message to DLQ (skip)
                        sqs.change_message_visibility(
                            QueueUrl=DLQ_URL,
                            ReceiptHandle=message["ReceiptHandle"],
                            VisibilityTimeout=0,
                        )
                        skipped_count += 1

                except Exception as e:
                    log_structured(
                        logger,
                        "ERROR",
                        "Failed to redrive message",
                        request_id,
                        messageId=message.get("MessageId"),
                        error=str(e),
                    )

                    # Return message to DLQ on error
                    try:
                        sqs.change_message_visibility(
                            QueueUrl=DLQ_URL,
                            ReceiptHandle=message["ReceiptHandle"],
                            VisibilityTimeout=0,
                        )
                    except:
                        pass

                    skipped_count += 1

                if processed_count >= max_messages:
                    break

        log_structured(
            logger,
            "INFO",
            "Messages redriven",
            request_id,
            count=redriven_count,
            processed=processed_count,
            skipped=skipped_count,
        )

        redrive_stats = {
            "initialDlqCount": initial_dlq_count,
            "processedMessages": processed_count,
            "redrivenMessages": redriven_count,
            "skippedMessages": skipped_count,
            "completedAt": get_current_timestamp(),
        }

        return create_api_response(
            200,
            {
                "message": f"Redrive completed: {redriven_count} messages redriven",
                "redriveStats": redrive_stats,
            },
        )

    except Exception as e:
        log_structured(
            logger, "ERROR", "Failed to start redrive", request_id, error=str(e)
        )
        return create_api_response(500, {"error": "Failed to start redrive operation"})


def handle_cancel(body: dict, request_id: str):
    """
    Cancel redrive operation (placeholder for demonstration)
    """
    log_structured(logger, "INFO", "Redrive cancel requested", request_id)

    # In a real implementation, this would stop ongoing redrive operations
    # For this demo, we just return a success response
    return create_api_response(
        200,
        {
            "message": "Redrive cancellation acknowledged",
            "note": "This is a demonstration endpoint - no active operations to cancel",
        },
    )


def should_include_message(
    message: dict, error_type_filter: str, min_age_seconds: int
) -> bool:
    """
    Check if message should be included based on filters
    """
    # Check age filter
    if min_age_seconds > 0:
        # Calculate message age from first receive timestamp
        first_receive_timestamp = (
            int(message.get("Attributes", {}).get("SentTimestamp", 0)) / 1000
        )
        current_timestamp = time.time()
        message_age = current_timestamp - first_receive_timestamp

        if message_age < min_age_seconds:
            return False

    # Check error type filter
    if error_type_filter:
        message_attributes = message.get("MessageAttributes", {})
        error_type_candidate = message_attributes.get("errorTypeCandidate", {}).get(
            "StringValue", ""
        )

        if error_type_filter.lower() not in error_type_candidate.lower():
            return False

    return True


def format_message_preview(message: dict) -> dict:
    """
    Format message for preview display
    """
    try:
        body = json.loads(message["Body"])
    except:
        body = message["Body"]

    attributes = message.get("Attributes", {})
    message_attributes = message.get("MessageAttributes", {})

    # Calculate age
    sent_timestamp = int(attributes.get("SentTimestamp", 0)) / 1000
    age_seconds = int(time.time() - sent_timestamp) if sent_timestamp > 0 else 0

    return {
        "messageId": message["MessageId"],
        "body": body,
        "ageSeconds": age_seconds,
        "receiveCount": int(attributes.get("ApproximateReceiveCount", 0)),
        "firstReceiveTimestamp": attributes.get("ApproximateFirstReceiveTimestamp"),
        "messageAttributes": {
            key: attr.get("StringValue", attr.get("BinaryValue"))
            for key, attr in message_attributes.items()
        },
    }


def calculate_exponential_backoff(attempt: int, base_jitter_minutes: int = 5) -> int:
    """
    Calculate exponential backoff delay with jitter

    Args:
        attempt: The attempt number (receive count)
        base_jitter_minutes: Base jitter in minutes

    Returns:
        Delay in seconds (capped at 900 seconds / 15 minutes)
    """
    # Base delay: 2^attempt seconds, starting from 1 second
    base_delay = min(2 ** (attempt - 1), 300)  # Cap base at 5 minutes

    # Add jitter: random value between 0 and base_jitter_minutes * 60
    jitter = (
        random.randint(0, base_jitter_minutes * 60) if base_jitter_minutes > 0 else 0
    )

    # Total delay with jitter
    total_delay = base_delay + jitter

    # Cap at 15 minutes (SQS DelaySeconds maximum)
    return min(total_delay, 900)


def categorize_error_type(message: dict) -> str:
    """
    Categorize error type based on message attributes and content

    Args:
        message: SQS message dictionary

    Returns:
        Error category string
    """
    message_attributes = message.get("MessageAttributes", {})

    # Check for explicit error type in message attributes
    error_type_candidate = message_attributes.get("errorTypeCandidate", {}).get(
        "StringValue", ""
    )

    if error_type_candidate:
        # Map known error types
        error_type_upper = error_type_candidate.upper()
        if "VALIDATION" in error_type_upper or "SCHEMA" in error_type_upper:
            return "VALIDATION"
        elif "TIMEOUT" in error_type_upper:
            return "TIMEOUT"
        elif "TRANSIENT" in error_type_upper or "TEMPORARY" in error_type_upper:
            return "TRANSIENT"
        elif "PROCESSING" in error_type_upper or "BUSINESS" in error_type_upper:
            return "PROCESSING"
        elif "PERMANENT" in error_type_upper or "FATAL" in error_type_upper:
            return "PERMANENT"

    # Analyze message body for error patterns
    try:
        body = json.loads(message["Body"])

        # Check for validation-related errors in the payload
        if any(key in str(body).lower() for key in ["validation", "schema", "invalid"]):
            return "VALIDATION"

        # Check for timeout indicators
        if any(key in str(body).lower() for key in ["timeout", "slow", "deadline"]):
            return "TIMEOUT"

    except (json.JSONDecodeError, TypeError):
        pass

    # Check receive count to infer error type
    receive_count = int(message.get("Attributes", {}).get("ApproximateReceiveCount", 1))

    if receive_count >= 5:
        return "PERMANENT"  # Likely permanent after many retries
    elif receive_count >= 2:
        return "TRANSIENT"  # Likely transient if retrying

    return "UNKNOWN"
