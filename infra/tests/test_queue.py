"""
Tests for the Queue Stack
"""

import aws_cdk as cdk
import aws_cdk.assertions as assertions
from stacks.queue_stack import QueueStack


def test_queue_stack_creation():
    """Test that the queue stack creates the expected resources"""
    app = cdk.App()
    stack = QueueStack(app, "TestQueueStack")
    template = assertions.Template.from_stack(stack)

    # Test SQS queues are created
    template.has_resource_properties(
        "AWS::SQS::Queue", {"VisibilityTimeoutSeconds": 180}
    )

    # Test DLQ is created
    template.resource_count_is("AWS::SQS::Queue", 2)  # Main queue + DLQ

    # Test redrive policy is configured
    template.has_resource_properties(
        "AWS::SQS::Queue", {"RedrivePolicy": {"maxReceiveCount": 5}}
    )


def test_dynamodb_table_creation():
    """Test that DynamoDB table is created with correct configuration"""
    app = cdk.App()
    stack = QueueStack(app, "TestQueueStack")
    template = assertions.Template.from_stack(stack)

    # Test DynamoDB table is created
    template.has_resource_properties(
        "AWS::DynamoDB::Table",
        {
            "BillingMode": "PAY_PER_REQUEST",
            "TimeToLiveSpecification": {"AttributeName": "expiresAt", "Enabled": True},
        },
    )

    # Test partition key is correct
    template.has_resource_properties(
        "AWS::DynamoDB::Table",
        {"KeySchema": [{"AttributeName": "idempotencyKey", "KeyType": "HASH"}]},
    )


def test_eventbridge_bus_creation():
    """Test that EventBridge custom bus is created"""
    app = cdk.App()
    stack = QueueStack(app, "TestQueueStack")
    template = assertions.Template.from_stack(stack)

    # Test EventBridge custom bus is created
    template.has_resource_properties(
        "AWS::Events::EventBus",
        {"Name": assertions.Match.string_like_regexp("ingestion-events-.*")},
    )

    # Test SNS topic is created
    template.has_resource_properties(
        "AWS::SNS::Topic", {"DisplayName": "Ingestion Pipeline Notifications"}
    )


def test_ssm_parameters_creation():
    """Test that SSM parameters are created"""
    app = cdk.App()
    stack = QueueStack(app, "TestQueueStack")
    template = assertions.Template.from_stack(stack)

    # Test failure mode parameter
    template.has_resource_properties(
        "AWS::SSM::Parameter",
        {"Name": "/ingestion/failure_mode", "Type": "String", "Value": "none"},
    )

    # Test that multiple SSM parameters are created
    template.resource_count_is(
        "AWS::SSM::Parameter", 5
    )  # failure_mode, queue_url, dlq_url, event_bus_name, idempotency_table


def test_kms_key_when_enabled():
    """Test KMS key creation when CMK is enabled"""
    app = cdk.App(context={"useKmsCmk": True})
    stack = QueueStack(app, "TestQueueStack")
    template = assertions.Template.from_stack(stack)

    # Test KMS key is created
    template.has_resource_properties("AWS::KMS::Key", {"EnableKeyRotation": True})

    # Test KMS alias is created
    template.has_resource_properties(
        "AWS::KMS::Alias",
        {"AliasName": assertions.Match.string_like_regexp("alias/ingestion-lab-.*")},
    )


def test_queue_encryption_configuration():
    """Test queue encryption configuration"""
    app = cdk.App()
    stack = QueueStack(app, "TestQueueStack")
    template = assertions.Template.from_stack(stack)

    # Test SQS managed encryption (default)
    template.has_resource_properties("AWS::SQS::Queue", {"SqsManagedSseEnabled": True})


def test_security_best_practices():
    """Test security best practices are implemented"""
    app = cdk.App()
    stack = QueueStack(app, "TestQueueStack")
    template = assertions.Template.from_stack(stack)

    # Test DynamoDB table has point-in-time recovery disabled for dev
    template.has_resource_properties(
        "AWS::DynamoDB::Table",
        {"PointInTimeRecoverySpecification": {"PointInTimeRecoveryEnabled": False}},
    )


def test_context_configuration():
    """Test that context values are properly applied"""
    app = cdk.App(context={"envName": "test", "maxReceiveCount": 3, "ttlDays": 14})
    stack = QueueStack(app, "TestQueueStack")
    template = assertions.Template.from_stack(stack)

    # Test max receive count is applied
    template.has_resource_properties(
        "AWS::SQS::Queue", {"RedrivePolicy": {"maxReceiveCount": 3}}
    )

    # Test environment name is used in resource names
    template.has_resource_properties(
        "AWS::SQS::Queue", {"QueueName": assertions.Match.string_like_regexp(".*-test")}
    )
