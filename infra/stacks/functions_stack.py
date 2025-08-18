"""
Lambda Functions Stack for the ingestion pipeline
"""

from aws_cdk import (
    Stack,
    Duration,
    aws_lambda as lambda_,
    aws_lambda_event_sources as lambda_event_sources,
    aws_iam as iam,
)
from constructs import Construct
from cdk_constructs.lambda_fn import ObservableLambda
from .queue_stack import QueueStack


class FunctionsStack(Stack):
    """
    Stack containing all Lambda functions for the ingestion pipeline
    """

    def __init__(
        self, scope: Construct, construct_id: str, queue_stack: QueueStack, **kwargs
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Get context values
        env_name = self.node.try_get_context("envName") or "dev"
        batch_size = self.node.try_get_context("batchSize") or 10
        max_batching_window_seconds = (
            self.node.try_get_context("maxBatchingWindowSeconds") or 2
        )
        worker_timeout_seconds = self.node.try_get_context("workerTimeoutSeconds") or 30
        ingest_timeout_seconds = self.node.try_get_context("ingestTimeoutSeconds") or 15
        redrive_timeout_seconds = (
            self.node.try_get_context("redriveTimeoutSeconds") or 60
        )

        # Store queue stack reference
        self.queue_stack = queue_stack

        # Common environment variables for all functions
        common_env_vars = {
            "QUEUE_URL": queue_stack.queue_url,
            "DLQ_URL": queue_stack.dlq_url,
            "EVENT_BUS_NAME": queue_stack.event_bus.bus_name,
            "IDEMPOTENCY_TABLE": queue_stack.idempotency_table.table_name,
            "ENV_NAME": env_name,
        }

        # Create Ingest Lambda
        self.ingest_function = ObservableLambda(
            self,
            "IngestFunction",
            function_name=f"ingestion-ingest-{env_name}",
            handler="handler.lambda_handler",
            code_path="../functions/ingest",
            timeout=Duration.seconds(ingest_timeout_seconds),
            environment_variables=common_env_vars,
            encryption_key=queue_stack.kms_key,
            memory_size=256,
        )

        # Grant ingest function permissions
        queue_stack.sqs_construct.grant_send_messages(self.ingest_function.function)
        queue_stack.event_bus.grant_put_events(self.ingest_function.function)

        # Add SSM parameter read permissions
        self.ingest_function.add_policy_statement(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["ssm:GetParameter"],
                resources=[queue_stack.failure_mode_parameter.parameter_arn],
            )
        )

        # Create Worker Lambda
        self.worker_function = ObservableLambda(
            self,
            "WorkerFunction",
            function_name=f"ingestion-worker-{env_name}",
            handler="handler.lambda_handler",
            code_path="../functions/worker",
            timeout=Duration.seconds(worker_timeout_seconds),
            environment_variables=common_env_vars,
            encryption_key=queue_stack.kms_key,
            memory_size=512,
            reserved_concurrency=10,  # Limit concurrency to control throughput
        )

        # Grant worker function permissions
        queue_stack.sqs_construct.grant_consume_messages(self.worker_function.function)
        queue_stack.event_bus.grant_put_events(self.worker_function.function)
        queue_stack.idempotency_table.grant_read_write_data(
            self.worker_function.function
        )

        # Add SSM parameter read permissions
        self.worker_function.add_policy_statement(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["ssm:GetParameter"],
                resources=[queue_stack.failure_mode_parameter.parameter_arn],
            )
        )

        # Add SQS event source to worker function
        self.worker_function.add_event_source(
            lambda_event_sources.SqsEventSource(
                queue_stack.queue,
                batch_size=batch_size,
                max_batching_window=Duration.seconds(max_batching_window_seconds),
                report_batch_item_failures=True,  # Enable partial batch response
            )
        )

        # Create Redrive Lambda
        self.redrive_function = ObservableLambda(
            self,
            "RedriveFunction",
            function_name=f"ingestion-redrive-{env_name}",
            handler="handler.lambda_handler",
            code_path="../functions/redrive",
            timeout=Duration.seconds(redrive_timeout_seconds),
            environment_variables=common_env_vars,
            encryption_key=queue_stack.kms_key,
            memory_size=256,
        )

        # Grant redrive function permissions
        queue_stack.sqs_construct.grant_dlq_consume_messages(
            self.redrive_function.function
        )
        queue_stack.sqs_construct.grant_send_messages(self.redrive_function.function)

        # Add additional permissions for redrive operations
        self.redrive_function.add_policy_statement(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "sqs:ReceiveMessage",
                    "sqs:DeleteMessage",
                    "sqs:GetQueueAttributes",
                ],
                resources=[queue_stack.dlq_arn],
            )
        )

        # Create metric filters for structured logging
        self._create_metric_filters()

        # Store function references
        self.functions = {
            "ingest": self.ingest_function.function,
            "worker": self.worker_function.function,
            "redrive": self.redrive_function.function,
        }

    def _create_metric_filters(self):
        """Create CloudWatch metric filters for structured logging"""

        # Error type metric filter for worker function
        self.worker_function.create_metric_filter(
            filter_name="ErrorType",
            filter_pattern='[timestamp, request_id, level="ERROR", message, error_type]',
            metric_name="ErrorsByType",
            metric_namespace="IngestionLab/Worker",
        )

        # Processed messages metric filter for worker function
        self.worker_function.create_metric_filter(
            filter_name="ProcessedMessages",
            filter_pattern='[timestamp, request_id, level="INFO", message="Message processed", processed="true"]',
            metric_name="ProcessedMessages",
            metric_namespace="IngestionLab/Worker",
            default_value=1,
        )

        # Idempotency hits metric filter for worker function
        self.worker_function.create_metric_filter(
            filter_name="IdempotencyHits",
            filter_pattern='[timestamp, request_id, level="INFO", message="Idempotent message", idempotent="true"]',
            metric_name="IdempotentMessages",
            metric_namespace="IngestionLab/Worker",
            default_value=1,
        )

        # Ingest validation errors
        self.ingest_function.create_metric_filter(
            filter_name="ValidationErrors",
            filter_pattern='[timestamp, request_id, level="ERROR", message="Validation failed"]',
            metric_name="ValidationErrors",
            metric_namespace="IngestionLab/Ingest",
            default_value=1,
        )

        # Redrive operations
        self.redrive_function.create_metric_filter(
            filter_name="RedriveOperations",
            filter_pattern='[timestamp, request_id, level="INFO", message="Messages redriven", count]',
            metric_name="RedrivenMessages",
            metric_namespace="IngestionLab/Redrive",
        )
