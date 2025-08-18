"""
EventBridge custom bus construct for ingestion events
"""

from aws_cdk import (
    aws_events as events,
    aws_events_targets as targets,
    aws_sns as sns,
    aws_kms as kms,
    aws_iam as iam,
)
from constructs import Construct
from typing import Optional


class IngestionEventBus(Construct):
    """
    Custom EventBridge bus for ingestion pipeline events with SNS integration
    """

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        bus_name: str,
        encryption_key: Optional[kms.IKey] = None,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Get context values
        env_name = self.node.try_get_context("envName") or "dev"
        alarm_email = self.node.try_get_context("alarmEmail") or "devops@example.com"

        # Create custom event bus
        self.event_bus = events.EventBus(
            self, "IngestionEventBus", event_bus_name=bus_name
        )

        # Create SNS topic for notifications
        self.notification_topic = sns.Topic(
            self,
            "IngestionNotifications",
            topic_name=f"ingestion-notifications-{env_name}",
            display_name="Ingestion Pipeline Notifications",
            master_key=encryption_key,
        )

        # Add email subscription if provided
        if alarm_email and alarm_email != "devops@example.com":
            self.notification_topic.add_subscription(
                sns.Subscription(
                    self,
                    "EmailSubscription",
                    topic=self.notification_topic,
                    endpoint=alarm_email,
                    protocol=sns.SubscriptionProtocol.EMAIL,
                )
            )

        # Create rule for ingestion success events
        self.success_rule = events.Rule(
            self,
            "IngestionSuccessRule",
            event_bus=self.event_bus,
            rule_name=f"ingestion-success-{env_name}",
            description="Route ingestion success events to SNS",
            event_pattern=events.EventPattern(
                source=["ingestion.pipeline"],
                detail_type=["Ingestion Success"],
                detail={"status": ["SUCCEEDED"]},
            ),
            targets=[
                targets.SnsTopic(
                    self.notification_topic,
                    message=events.RuleTargetInput.from_text(
                        "✅ Ingestion Success\n"
                        "Event ID: {$.detail.eventId}\n"
                        "Idempotency Key: {$.detail.idempotencyKey}\n"
                        "Processed At: {$.detail.processedAt}\n"
                        "Duration: {$.detail.durationMs}ms"
                    ),
                )
            ],
        )

        # Create rule for ingestion failure events
        self.failure_rule = events.Rule(
            self,
            "IngestionFailureRule",
            event_bus=self.event_bus,
            rule_name=f"ingestion-failure-{env_name}",
            description="Route ingestion failure events to SNS",
            event_pattern=events.EventPattern(
                source=["ingestion.pipeline"],
                detail_type=["Ingestion Failure"],
                detail={"status": ["FAILED"]},
            ),
            targets=[
                targets.SnsTopic(
                    self.notification_topic,
                    message=events.RuleTargetInput.from_text(
                        "❌ Ingestion Failure\n"
                        "Event ID: {$.detail.eventId}\n"
                        "Idempotency Key: {$.detail.idempotencyKey}\n"
                        "Error Type: {$.detail.errorType}\n"
                        "Error Message: {$.detail.errorMessage}\n"
                        "Failed At: {$.detail.failedAt}"
                    ),
                )
            ],
        )

        # Store references
        self.bus_name = bus_name
        self.bus_arn = self.event_bus.event_bus_arn
        self.topic_arn = self.notification_topic.topic_arn

    def grant_put_events(self, grantee):
        """Grant permissions to put events to the custom bus"""
        grantee.add_to_role_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["events:PutEvents"],
                resources=[self.event_bus.event_bus_arn],
            )
        )

    def add_rule(
        self,
        rule_id: str,
        rule_name: str,
        description: str,
        event_pattern: events.EventPattern,
        targets: list,
    ) -> events.Rule:
        """Add a custom rule to the event bus"""
        return events.Rule(
            self,
            rule_id,
            event_bus=self.event_bus,
            rule_name=rule_name,
            description=description,
            event_pattern=event_pattern,
            targets=targets,
        )

    def create_lambda_target_rule(
        self,
        rule_id: str,
        rule_name: str,
        description: str,
        event_pattern: events.EventPattern,
        target_function,
    ) -> events.Rule:
        """Create a rule that targets a Lambda function"""
        return self.add_rule(
            rule_id=rule_id,
            rule_name=rule_name,
            description=description,
            event_pattern=event_pattern,
            targets=[targets.LambdaFunction(target_function)],
        )
