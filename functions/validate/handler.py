"""
Validation Lambda function - handles schema validation only
Separated from ingest for single responsibility principle
"""

import json
import os
import sys

# Add common utilities to path
sys.path.append("/opt/python")
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "common"))

from utils import (
    setup_logger,
    validate_event_payload,
    get_failure_mode,
    should_simulate_failure,
    get_current_timestamp,
    parse_api_gateway_event,
    create_api_response,
    log_structured,
)

# Initialize logger
logger = setup_logger(__name__)

# Environment variables
ENV_NAME = os.environ["ENV_NAME"]


def lambda_handler(event, context):
    """
    Main Lambda handler for validation only
    """
    request_id = context.aws_request_id

    try:
        # Parse the incoming event
        method, body, query_params = parse_api_gateway_event(event)

        # Handle health check
        if event.get("rawPath") == "/validate/health":
            return handle_health_check(request_id)

        # Only accept POST requests for /validate
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

        # Check if we should simulate validation failure
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

        log_structured(
            logger,
            "INFO",
            "Validation successful",
            request_id,
            payloadSize=len(json.dumps(body)),
        )

        # Return validated payload with metadata
        validated_payload = {
            **body,
            "validatedAt": get_current_timestamp(),
            "requestId": request_id,
            "validationStatus": "PASSED",
        }

        return create_api_response(
            200,
            {
                "message": "Validation successful",
                "validatedPayload": validated_payload,
            },
        )

    except Exception as e:
        log_structured(
            logger,
            "ERROR",
            "Unexpected error in validation handler",
            request_id,
            error=str(e),
            errorType=type(e).__name__,
        )

        return create_api_response(500, {"error": "Internal server error"})


def handle_health_check(request_id: str):
    """
    Handle health check endpoint
    """
    log_structured(logger, "INFO", "Health check passed", request_id, status="healthy")

    return create_api_response(
        200,
        {
            "status": "healthy",
            "service": "validation-api",
            "environment": ENV_NAME,
            "timestamp": get_current_timestamp(),
        },
    )
