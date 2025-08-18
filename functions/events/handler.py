"""
Events Lambda function - handles EventBridge event publishing only
Separated from worker for single responsibility principle
"""

import json
import os
import sys
import boto3

# Add common utilities to path
sys.path.append("/opt/python")
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "common"))

from utils import (
    setup_logger,
    put_eventbridge_event,
    get_current_timestamp,
    log_structured,
)

# Initialize logger
logger = setup_logger(__name__)

# Environment variables
EVENT_BUS_NAME = os.environ["EVENT_BUS_NAME"]
ENV_NAME = os.environ["ENV_NAME"]


def lambda_handler(event, context):
    """
    Main Lambda handler for event publishing
    """
    request_id = context.aws_request_id

    log_structured(
        logger,
        "INFO",
        "Event publishing started",
        request_id,
        recordCount=len(event.get("processingResults", [])),
    )

    # Process results from business logic processing
    processing_results = event.get("processingResults", [])
    batch_item_failures = event.get("batchItemFailures", [])
    published_events = []

    for result in processing_results:
        try:
            if result["success"]:
                # Publish success event
                event_published = publish_success_event(result, request_id)
                if event_published:
                    published_events.append(
                        {
                            "type": "success",
                            "idempotencyKey": result["idempotencyKey"],
                            "messageId": result["messageId"],
                        }
                    )
            else:
                # Publish failure event
                event_published = publish_failure_event(result, request_id)
                if event_published:
                    published_events.append(
                        {
                            "type": "failure",
                            "idempotencyKey": result["idempotencyKey"],
                            "messageId": result["messageId"],
                        }
                    )

        except Exception as e:
            log_structured(
                logger,
                "ERROR",
                "Failed to publish event",
                request_id,
                messageId=result.get("messageId"),
                idempotencyKey=result.get("idempotencyKey"),
                error=str(e),
                errorType=type(e).__name__,
            )

            # Add to batch failures - event publishing failure shouldn't stop message processing
            # but we should track it for monitoring
            pass

    # Final response
    response = {
        "batchItemFailures": batch_item_failures,
        "publishedEvents": published_events,
        "totalResults": len(processing_results),
        "publishedCount": len(published_events),
    }

    log_structured(
        logger,
        "INFO",
        "Event publishing completed",
        request_id,
        totalResults=len(processing_results),
        publishedCount=len(published_events),
        failedRecords=len(batch_item_failures),
    )

    return response


def publish_success_event(result: dict, request_id: str) -> bool:
    """
    Publish success event to EventBridge
    """
    try:
        payload = result.get("payload", {})

        event_detail = {
            "eventId": f"success-{result['idempotencyKey']}",
            "idempotencyKey": result["idempotencyKey"],
            "status": "SUCCEEDED",
            "orderId": payload.get("orderId"),
            "amount": payload.get("amount"),
            "processedAt": get_current_timestamp(),
            "requestId": request_id,
            "durationMs": result.get("durationMs", 0),
            "result": result.get("result", {}),
        }

        put_eventbridge_event(
            event_bus_name=EVENT_BUS_NAME,
            source="ingestion.pipeline",
            detail_type="Processing Success",
            detail=event_detail,
        )

        log_structured(
            logger,
            "INFO",
            "Success event published",
            request_id,
            idempotencyKey=result["idempotencyKey"],
            messageId=result["messageId"],
        )

        return True

    except Exception as e:
        log_structured(
            logger,
            "ERROR",
            "Failed to publish success event",
            request_id,
            idempotencyKey=result.get("idempotencyKey"),
            messageId=result.get("messageId"),
            error=str(e),
        )
        return False


def publish_failure_event(result: dict, request_id: str) -> bool:
    """
    Publish failure event to EventBridge
    """
    try:
        payload = result.get("payload", {})

        event_detail = {
            "eventId": f"failure-{result['idempotencyKey']}",
            "idempotencyKey": result["idempotencyKey"],
            "status": "FAILED",
            "orderId": payload.get("orderId"),
            "amount": payload.get("amount"),
            "errorType": result.get("errorType", "ProcessingError"),
            "errorMessage": result.get("error", "Unknown error"),
            "failedAt": get_current_timestamp(),
            "requestId": request_id,
        }

        put_eventbridge_event(
            event_bus_name=EVENT_BUS_NAME,
            source="ingestion.pipeline",
            detail_type="Processing Failure",
            detail=event_detail,
        )

        log_structured(
            logger,
            "INFO",
            "Failure event published",
            request_id,
            idempotencyKey=result["idempotencyKey"],
            messageId=result["messageId"],
            errorType=result.get("errorType"),
        )

        return True

    except Exception as e:
        log_structured(
            logger,
            "ERROR",
            "Failed to publish failure event",
            request_id,
            idempotencyKey=result.get("idempotencyKey"),
            messageId=result.get("messageId"),
            error=str(e),
        )
        return False


def publish_custom_event(event_type: str, detail: dict, request_id: str) -> bool:
    """
    Publish custom event to EventBridge
    """
    try:
        put_eventbridge_event(
            event_bus_name=EVENT_BUS_NAME,
            source="ingestion.pipeline",
            detail_type=event_type,
            detail=detail,
        )

        log_structured(
            logger,
            "INFO",
            "Custom event published",
            request_id,
            eventType=event_type,
        )

        return True

    except Exception as e:
        log_structured(
            logger,
            "ERROR",
            "Failed to publish custom event",
            request_id,
            eventType=event_type,
            error=str(e),
        )
        return False
