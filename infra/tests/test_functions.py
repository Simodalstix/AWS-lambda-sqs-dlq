"""
Tests for the Functions Stack
"""

import aws_cdk as cdk
import aws_cdk.assertions as assertions
from stacks.queue_stack import QueueStack
from stacks.functions_stack import FunctionsStack


def test_lambda_functions_creation():
    """Test that all Lambda functions are created"""
    app = cdk.App()
    queue_stack = QueueStack(app, "TestQueueStack")
    functions_stack = FunctionsStack(app, "TestFunctionsStack", queue_stack=queue_stack)
    template = assertions.Template.from_stack(functions_stack)

    # Test that 3 Lambda functions are created
    template.resource_count_is("AWS::Lambda::Function", 3)

    # Test function names
    template.has_resource_properties(
        "AWS::Lambda::Function",
        {"FunctionName": assertions.Match.string_like_regexp("ingestion-ingest-.*")},
    )

    template.has_resource_properties(
        "AWS::Lambda::Function",
        {"FunctionName": assertions.Match.string_like_regexp("ingestion-worker-.*")},
    )

    template.has_resource_properties(
        "AWS::Lambda::Function",
        {"FunctionName": assertions.Match.string_like_regexp("ingestion-redrive-.*")},
    )


def test_lambda_runtime_and_architecture():
    """Test Lambda runtime and architecture configuration"""
    app = cdk.App()
    queue_stack = QueueStack(app, "TestQueueStack")
    functions_stack = FunctionsStack(app, "TestFunctionsStack", queue_stack=queue_stack)
    template = assertions.Template.from_stack(functions_stack)

    # Test Python 3.11 runtime
    template.has_resource_properties("AWS::Lambda::Function", {"Runtime": "python3.11"})

    # Test ARM64 architecture
    template.has_resource_properties(
        "AWS::Lambda::Function", {"Architectures": ["arm64"]}
    )


def test_lambda_environment_variables():
    """Test Lambda environment variables are set correctly"""
    app = cdk.App()
    queue_stack = QueueStack(app, "TestQueueStack")
    functions_stack = FunctionsStack(app, "TestFunctionsStack", queue_stack=queue_stack)
    template = assertions.Template.from_stack(functions_stack)

    # Test common environment variables
    template.has_resource_properties(
        "AWS::Lambda::Function",
        {
            "Environment": {
                "Variables": {
                    "LOG_LEVEL": "INFO",
                    "POWERTOOLS_SERVICE_NAME": assertions.Match.any_value(),
                    "POWERTOOLS_METRICS_NAMESPACE": "IngestionLab",
                }
            }
        },
    )


def test_lambda_timeouts():
    """Test Lambda timeout configurations"""
    app = cdk.App(
        context={
            "workerTimeoutSeconds": 30,
            "ingestTimeoutSeconds": 15,
            "redriveTimeoutSeconds": 60,
        }
    )
    queue_stack = QueueStack(app, "TestQueueStack")
    functions_stack = FunctionsStack(app, "TestFunctionsStack", queue_stack=queue_stack)
    template = assertions.Template.from_stack(functions_stack)

    # Test worker timeout
    template.has_resource_properties(
        "AWS::Lambda::Function",
        {
            "FunctionName": assertions.Match.string_like_regexp(".*worker.*"),
            "Timeout": 30,
        },
    )

    # Test ingest timeout
    template.has_resource_properties(
        "AWS::Lambda::Function",
        {
            "FunctionName": assertions.Match.string_like_regexp(".*ingest.*"),
            "Timeout": 15,
        },
    )


def test_sqs_event_source_mapping():
    """Test SQS event source mapping for worker function"""
    app = cdk.App()
    queue_stack = QueueStack(app, "TestQueueStack")
    functions_stack = FunctionsStack(app, "TestFunctionsStack", queue_stack=queue_stack)
    template = assertions.Template.from_stack(functions_stack)

    # Test event source mapping exists
    template.has_resource_properties(
        "AWS::Lambda::EventSourceMapping",
        {
            "BatchSize": 10,
            "MaximumBatchingWindowInSeconds": 2,
            "FunctionResponseTypes": ["ReportBatchItemFailures"],
        },
    )


def test_iam_permissions():
    """Test IAM permissions are correctly configured"""
    app = cdk.App()
    queue_stack = QueueStack(app, "TestQueueStack")
    functions_stack = FunctionsStack(app, "TestFunctionsStack", queue_stack=queue_stack)
    template = assertions.Template.from_stack(functions_stack)

    # Test SQS permissions
    template.has_resource_properties(
        "AWS::IAM::Policy",
        {
            "PolicyDocument": {
                "Statement": assertions.Match.array_with(
                    [
                        assertions.Match.object_like(
                            {
                                "Effect": "Allow",
                                "Action": assertions.Match.array_with(
                                    ["sqs:SendMessage"]
                                ),
                            }
                        )
                    ]
                )
            }
        },
    )

    # Test DynamoDB permissions
    template.has_resource_properties(
        "AWS::IAM::Policy",
        {
            "PolicyDocument": {
                "Statement": assertions.Match.array_with(
                    [
                        assertions.Match.object_like(
                            {
                                "Effect": "Allow",
                                "Action": assertions.Match.array_with(
                                    [
                                        "dynamodb:PutItem",
                                        "dynamodb:UpdateItem",
                                        "dynamodb:GetItem",
                                    ]
                                ),
                            }
                        )
                    ]
                )
            }
        },
    )

    # Test EventBridge permissions
    template.has_resource_properties(
        "AWS::IAM::Policy",
        {
            "PolicyDocument": {
                "Statement": assertions.Match.array_with(
                    [
                        assertions.Match.object_like(
                            {"Effect": "Allow", "Action": ["events:PutEvents"]}
                        )
                    ]
                )
            }
        },
    )


def test_cloudwatch_log_groups():
    """Test CloudWatch log groups are created"""
    app = cdk.App()
    queue_stack = QueueStack(app, "TestQueueStack")
    functions_stack = FunctionsStack(app, "TestFunctionsStack", queue_stack=queue_stack)
    template = assertions.Template.from_stack(functions_stack)

    # Test log groups are created
    template.resource_count_is("AWS::Logs::LogGroup", 3)

    # Test log group names
    template.has_resource_properties(
        "AWS::Logs::LogGroup",
        {
            "LogGroupName": assertions.Match.string_like_regexp(
                "/aws/lambda/ingestion-.*"
            )
        },
    )


def test_metric_filters():
    """Test CloudWatch metric filters are created"""
    app = cdk.App()
    queue_stack = QueueStack(app, "TestQueueStack")
    functions_stack = FunctionsStack(app, "TestFunctionsStack", queue_stack=queue_stack)
    template = assertions.Template.from_stack(functions_stack)

    # Test metric filters are created
    template.resource_count_is("AWS::Logs::MetricFilter", 5)

    # Test specific metric filters
    template.has_resource_properties(
        "AWS::Logs::MetricFilter",
        {
            "MetricTransformations": [
                {
                    "MetricNamespace": "IngestionLab/Worker",
                    "MetricName": "ProcessedMessages",
                }
            ]
        },
    )


def test_lambda_insights():
    """Test Lambda Insights is enabled"""
    app = cdk.App()
    queue_stack = QueueStack(app, "TestQueueStack")
    functions_stack = FunctionsStack(app, "TestFunctionsStack", queue_stack=queue_stack)
    template = assertions.Template.from_stack(functions_stack)

    # Test Lambda Insights layer is attached
    template.has_resource_properties(
        "AWS::Lambda::Function",
        {
            "Layers": assertions.Match.array_with(
                [assertions.Match.string_like_regexp(".*LambdaInsightsExtension.*")]
            )
        },
    )


def test_x_ray_tracing():
    """Test X-Ray tracing is enabled"""
    app = cdk.App()
    queue_stack = QueueStack(app, "TestQueueStack")
    functions_stack = FunctionsStack(app, "TestFunctionsStack", queue_stack=queue_stack)
    template = assertions.Template.from_stack(functions_stack)

    # Test X-Ray tracing is enabled
    template.has_resource_properties(
        "AWS::Lambda::Function", {"TracingConfig": {"Mode": "Active"}}
    )


def test_worker_reserved_concurrency():
    """Test worker function has reserved concurrency"""
    app = cdk.App()
    queue_stack = QueueStack(app, "TestQueueStack")
    functions_stack = FunctionsStack(app, "TestFunctionsStack", queue_stack=queue_stack)
    template = assertions.Template.from_stack(functions_stack)

    # Test worker function has reserved concurrency
    template.has_resource_properties(
        "AWS::Lambda::Function",
        {
            "FunctionName": assertions.Match.string_like_regexp(".*worker.*"),
            "ReservedConcurrencyLimit": 10,
        },
    )


def test_ssm_parameter_permissions():
    """Test SSM parameter read permissions"""
    app = cdk.App()
    queue_stack = QueueStack(app, "TestQueueStack")
    functions_stack = FunctionsStack(app, "TestFunctionsStack", queue_stack=queue_stack)
    template = assertions.Template.from_stack(functions_stack)

    # Test SSM GetParameter permissions
    template.has_resource_properties(
        "AWS::IAM::Policy",
        {
            "PolicyDocument": {
                "Statement": assertions.Match.array_with(
                    [
                        assertions.Match.object_like(
                            {
                                "Effect": "Allow",
                                "Action": ["ssm:GetParameter"],
                                "Resource": assertions.Match.string_like_regexp(
                                    ".*parameter/ingestion/failure_mode"
                                ),
                            }
                        )
                    ]
                )
            }
        },
    )


def test_context_configuration():
    """Test context values are properly applied"""
    app = cdk.App(
        context={
            "batchSize": 5,
            "maxBatchingWindowSeconds": 10,
            "workerTimeoutSeconds": 45,
        }
    )
    queue_stack = QueueStack(app, "TestQueueStack")
    functions_stack = FunctionsStack(app, "TestFunctionsStack", queue_stack=queue_stack)
    template = assertions.Template.from_stack(functions_stack)

    # Test batch size configuration
    template.has_resource_properties(
        "AWS::Lambda::EventSourceMapping",
        {"BatchSize": 5, "MaximumBatchingWindowInSeconds": 10},
    )

    # Test worker timeout
    template.has_resource_properties(
        "AWS::Lambda::Function",
        {
            "FunctionName": assertions.Match.string_like_regexp(".*worker.*"),
            "Timeout": 45,
        },
    )
