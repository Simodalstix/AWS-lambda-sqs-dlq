"""
SQS Queue with Dead Letter Queue construct
"""

from aws_cdk import aws_sqs as sqs, aws_kms as kms, Duration
from constructs import Construct
from typing import Optional


class SqsWithDlq(Construct):
    """
    SQS queue with dead letter queue and configurable redrive policy
    """

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        queue_name: str,
        dlq_name: str,
        visibility_timeout: Duration,
        max_receive_count: int = 5,
        encryption_key: Optional[kms.IKey] = None,
        **kwargs
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Get context values
        use_kms_cmk = self.node.try_get_context("useKmsCmk") or False

        # Determine encryption configuration
        if use_kms_cmk and encryption_key:
            encryption = sqs.QueueEncryption.KMS
            encryption_master_key = encryption_key
        else:
            encryption = sqs.QueueEncryption.SQS_MANAGED
            encryption_master_key = None

        # Create Dead Letter Queue first
        self.dlq = sqs.Queue(
            self,
            "DeadLetterQueue",
            queue_name=dlq_name,
            encryption=encryption,
            encryption_master_key=encryption_master_key,
            # DLQ should have longer retention for investigation
            message_retention_period=Duration.days(14),
            # DLQ doesn't need its own DLQ
            visibility_timeout=Duration.minutes(5),
        )

        # Create main queue with DLQ redrive policy
        self.queue = sqs.Queue(
            self,
            "MainQueue",
            queue_name=queue_name,
            encryption=encryption,
            encryption_master_key=encryption_master_key,
            visibility_timeout=visibility_timeout,
            message_retention_period=Duration.days(4),
            dead_letter_queue=sqs.DeadLetterQueue(
                max_receive_count=max_receive_count, queue=self.dlq
            ),
            # Enable content-based deduplication for FIFO queues if needed
            # fifo=False by default for standard queues
        )

        # Store configuration for reference
        self.max_receive_count = max_receive_count
        self.visibility_timeout = visibility_timeout

    @property
    def queue_arn(self) -> str:
        """Return the main queue ARN"""
        return self.queue.queue_arn

    @property
    def queue_url(self) -> str:
        """Return the main queue URL"""
        return self.queue.queue_url

    @property
    def queue_name_value(self) -> str:
        """Return the main queue name"""
        return self.queue.queue_name

    @property
    def dlq_arn(self) -> str:
        """Return the DLQ ARN"""
        return self.dlq.queue_arn

    @property
    def dlq_url(self) -> str:
        """Return the DLQ URL"""
        return self.dlq.queue_url

    @property
    def dlq_name_value(self) -> str:
        """Return the DLQ name"""
        return self.dlq.queue_name

    def grant_send_messages(self, grantee):
        """Grant send message permissions to the main queue"""
        return self.queue.grant_send_messages(grantee)

    def grant_consume_messages(self, grantee):
        """Grant consume message permissions to the main queue"""
        return self.queue.grant_consume_messages(grantee)

    def grant_dlq_consume_messages(self, grantee):
        """Grant consume message permissions to the DLQ"""
        return self.dlq.grant_consume_messages(grantee)

    def grant_dlq_send_messages(self, grantee):
        """Grant send message permissions to the DLQ (for redrive)"""
        return self.dlq.grant_send_messages(grantee)
