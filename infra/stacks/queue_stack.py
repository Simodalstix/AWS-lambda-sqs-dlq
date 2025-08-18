"""
SQS Queue Stack with DLQ for the ingestion pipeline
"""

from aws_cdk import (
    Stack,
    Duration,
    aws_dynamodb as dynamodb,
    aws_ssm as ssm,
    RemovalPolicy,
)
from constructs import Construct
from cdk_constructs.kms_key import IngestionKmsKey
from cdk_constructs.sqs_with_dlq import SqsWithDlq
from cdk_constructs.event_bus import IngestionEventBus


class QueueStack(Stack):
    """
    Stack containing SQS queues, DynamoDB table, EventBridge bus, and SSM parameters
    """

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Get context values
        env_name = self.node.try_get_context("envName") or "dev"
        max_receive_count = self.node.try_get_context("maxReceiveCount") or 5
        worker_timeout_seconds = self.node.try_get_context("workerTimeoutSeconds") or 30

        # Calculate visibility timeout: Lambda timeout + buffer (AWS best practice)
        queue_visibility_seconds = max(
            worker_timeout_seconds + 30,  # 30s buffer for processing overhead
            self.node.try_get_context("queueVisibilitySeconds") or 180,
        )
        use_kms_cmk = self.node.try_get_context("useKmsCmk") or False
        ttl_days = self.node.try_get_context("ttlDays") or 7

        # Create KMS key if CMK is enabled
        self.kms_key = None
        if use_kms_cmk:
            kms_construct = IngestionKmsKey(self, "KmsKey")
            self.kms_key = kms_construct.key

        # Create SQS queues with DLQ
        self.sqs_construct = SqsWithDlq(
            self,
            "IngestionQueues",
            queue_name=f"ingestion-queue-{env_name}",
            dlq_name=f"ingestion-dlq-{env_name}",
            visibility_timeout=Duration.seconds(queue_visibility_seconds),
            max_receive_count=max_receive_count,
            encryption_key=self.kms_key,
        )

        # Create EventBridge custom bus
        self.event_bus = IngestionEventBus(
            self,
            "EventBus",
            bus_name=f"ingestion-events-{env_name}",
            encryption_key=self.kms_key,
        )

        # Create DynamoDB table for idempotency
        self.idempotency_table = dynamodb.Table(
            self,
            "IdempotencyTable",
            table_name=f"ingestion-state-{env_name}",
            partition_key=dynamodb.Attribute(
                name="idempotencyKey", type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            encryption=(
                dynamodb.TableEncryption.AWS_MANAGED
                if not use_kms_cmk
                else dynamodb.TableEncryption.CUSTOMER_MANAGED
            ),
            encryption_key=self.kms_key if use_kms_cmk else None,
            time_to_live_attribute="expiresAt",
            removal_policy=(
                RemovalPolicy.DESTROY if env_name == "dev" else RemovalPolicy.RETAIN
            ),
            point_in_time_recovery=env_name != "dev",
        )

        # Create SSM parameter for failure mode configuration
        self.failure_mode_parameter = ssm.StringParameter(
            self,
            "FailureModeParameter",
            parameter_name="/ingestion/failure_mode",
            string_value="none",
            description="Controls failure simulation modes: none, poison_payload, slow_downstream, random_fail_p30, duplicate_submit",
            tier=ssm.ParameterTier.STANDARD,
        )

        # Create SSM parameters for configuration
        ssm.StringParameter(
            self,
            "QueueUrlParameter",
            parameter_name="/ingestion/queue_url",
            string_value=self.sqs_construct.queue_url,
            description="Main SQS queue URL",
        )

        ssm.StringParameter(
            self,
            "DlqUrlParameter",
            parameter_name="/ingestion/dlq_url",
            string_value=self.sqs_construct.dlq_url,
            description="Dead letter queue URL",
        )

        ssm.StringParameter(
            self,
            "EventBusNameParameter",
            parameter_name="/ingestion/event_bus_name",
            string_value=self.event_bus.bus_name,
            description="EventBridge custom bus name",
        )

        ssm.StringParameter(
            self,
            "IdempotencyTableParameter",
            parameter_name="/ingestion/idempotency_table",
            string_value=self.idempotency_table.table_name,
            description="DynamoDB idempotency table name",
        )

        # Store references for other stacks
        self.queue = self.sqs_construct.queue
        self.dlq = self.sqs_construct.dlq
        self.queue_url = self.sqs_construct.queue_url
        self.dlq_url = self.sqs_construct.dlq_url
        self.queue_arn = self.sqs_construct.queue_arn
        self.dlq_arn = self.sqs_construct.dlq_arn
        self.event_bus_arn = self.event_bus.bus_arn
        self.notification_topic_arn = self.event_bus.topic_arn
