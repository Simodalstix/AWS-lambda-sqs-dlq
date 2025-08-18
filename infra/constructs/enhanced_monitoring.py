"""
Enhanced monitoring construct for the improved architecture
Includes CloudWatch dashboards, alarms, and custom metrics
"""

from aws_cdk import (
    Duration,
    aws_cloudwatch as cloudwatch,
    aws_cloudwatch_actions as cw_actions,
    aws_sns as sns,
    aws_logs as logs,
)
from constructs import Construct
from typing import List, Dict, Any


class EnhancedMonitoring(Construct):
    """
    Enhanced monitoring construct with comprehensive observability
    """

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        function_names: Dict[str, str],
        queue_names: Dict[str, str],
        table_name: str,
        event_bus_name: str,
        env_name: str = "dev",
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.function_names = function_names
        self.queue_names = queue_names
        self.table_name = table_name
        self.event_bus_name = event_bus_name
        self.env_name = env_name

        # Create SNS topic for alerts
        self.alert_topic = sns.Topic(
            self,
            "AlertTopic",
            topic_name=f"ingestion-alerts-{env_name}",
            display_name="Ingestion Pipeline Alerts",
        )

        # Create CloudWatch dashboard
        self.dashboard = self._create_dashboard()

        # Create alarms
        self.alarms = self._create_alarms()

        # Create custom metrics
        self._create_custom_metrics()

    def _create_dashboard(self) -> cloudwatch.Dashboard:
        """Create comprehensive CloudWatch dashboard"""
        dashboard = cloudwatch.Dashboard(
            self,
            "IngestionDashboard",
            dashboard_name=f"ingestion-pipeline-{self.env_name}",
            period_override=cloudwatch.PeriodOverride.AUTO,
        )

        # Function performance widgets
        function_widgets = self._create_function_widgets()

        # Queue metrics widgets
        queue_widgets = self._create_queue_widgets()

        # Error analysis widgets
        error_widgets = self._create_error_widgets()

        # Business metrics widgets
        business_widgets = self._create_business_widgets()

        # Add widgets to dashboard
        dashboard.add_widgets(*function_widgets)
        dashboard.add_widgets(*queue_widgets)
        dashboard.add_widgets(*error_widgets)
        dashboard.add_widgets(*business_widgets)

        return dashboard

    def _create_function_widgets(self) -> List[cloudwatch.IWidget]:
        """Create Lambda function performance widgets"""
        widgets = []

        # Function duration comparison
        duration_widget = cloudwatch.GraphWidget(
            title="Function Duration Comparison",
            left=[
                cloudwatch.Metric(
                    namespace="AWS/Lambda",
                    metric_name="Duration",
                    dimensions_map={"FunctionName": func_name},
                    statistic="Average",
                    label=func_type.title(),
                )
                for func_type, func_name in self.function_names.items()
            ],
            width=12,
            height=6,
        )
        widgets.append(duration_widget)

        # Function invocation rates
        invocation_widget = cloudwatch.GraphWidget(
            title="Function Invocation Rates",
            left=[
                cloudwatch.Metric(
                    namespace="AWS/Lambda",
                    metric_name="Invocations",
                    dimensions_map={"FunctionName": func_name},
                    statistic="Sum",
                    label=func_type.title(),
                )
                for func_type, func_name in self.function_names.items()
            ],
            width=12,
            height=6,
        )
        widgets.append(invocation_widget)

        # Error rates
        error_widget = cloudwatch.GraphWidget(
            title="Function Error Rates",
            left=[
                cloudwatch.Metric(
                    namespace="AWS/Lambda",
                    metric_name="Errors",
                    dimensions_map={"FunctionName": func_name},
                    statistic="Sum",
                    label=f"{func_type.title()} Errors",
                )
                for func_type, func_name in self.function_names.items()
            ],
            width=12,
            height=6,
        )
        widgets.append(error_widget)

        return widgets

    def _create_queue_widgets(self) -> List[cloudwatch.IWidget]:
        """Create SQS queue monitoring widgets"""
        widgets = []

        # Queue depth
        queue_depth_widget = cloudwatch.GraphWidget(
            title="Queue Depths",
            left=[
                cloudwatch.Metric(
                    namespace="AWS/SQS",
                    metric_name="ApproximateNumberOfMessages",
                    dimensions_map={"QueueName": queue_name},
                    statistic="Average",
                    label=queue_type.replace("_", " ").title(),
                )
                for queue_type, queue_name in self.queue_names.items()
            ],
            width=12,
            height=6,
        )
        widgets.append(queue_depth_widget)

        # Message age
        message_age_widget = cloudwatch.GraphWidget(
            title="Message Age (Oldest)",
            left=[
                cloudwatch.Metric(
                    namespace="AWS/SQS",
                    metric_name="ApproximateAgeOfOldestMessage",
                    dimensions_map={"QueueName": self.queue_names["main_queue"]},
                    statistic="Maximum",
                    label="Main Queue",
                ),
                cloudwatch.Metric(
                    namespace="AWS/SQS",
                    metric_name="ApproximateAgeOfOldestMessage",
                    dimensions_map={"QueueName": self.queue_names["dlq"]},
                    statistic="Maximum",
                    label="DLQ",
                ),
            ],
            width=12,
            height=6,
        )
        widgets.append(message_age_widget)

        return widgets

    def _create_error_widgets(self) -> List[cloudwatch.IWidget]:
        """Create error analysis widgets"""
        widgets = []

        # Error categorization (custom metric)
        error_category_widget = cloudwatch.GraphWidget(
            title="Error Categories",
            left=[
                cloudwatch.Metric(
                    namespace="IngestionPipeline",
                    metric_name="ErrorCount",
                    dimensions_map={
                        "ErrorType": error_type,
                        "Environment": self.env_name,
                    },
                    statistic="Sum",
                    label=error_type,
                )
                for error_type in [
                    "VALIDATION",
                    "TRANSIENT",
                    "PERMANENT",
                    "TIMEOUT",
                    "PROCESSING",
                ]
            ],
            width=12,
            height=6,
        )
        widgets.append(error_category_widget)

        # Circuit breaker states
        circuit_breaker_widget = cloudwatch.GraphWidget(
            title="Circuit Breaker States",
            left=[
                cloudwatch.Metric(
                    namespace="IngestionPipeline",
                    metric_name="CircuitBreakerState",
                    dimensions_map={
                        "Service": service,
                        "State": state,
                        "Environment": self.env_name,
                    },
                    statistic="Sum",
                    label=f"{service}-{state}",
                )
                for service in ["DynamoDB", "SQS", "EventBridge"]
                for state in ["OPEN", "CLOSED", "HALF_OPEN"]
            ],
            width=12,
            height=6,
        )
        widgets.append(circuit_breaker_widget)

        return widgets

    def _create_business_widgets(self) -> List[cloudwatch.IWidget]:
        """Create business metrics widgets"""
        widgets = []

        # Processing throughput
        throughput_widget = cloudwatch.GraphWidget(
            title="Processing Throughput",
            left=[
                cloudwatch.Metric(
                    namespace="IngestionPipeline",
                    metric_name="MessagesProcessed",
                    dimensions_map={"Status": "SUCCESS", "Environment": self.env_name},
                    statistic="Sum",
                    label="Successful",
                ),
                cloudwatch.Metric(
                    namespace="IngestionPipeline",
                    metric_name="MessagesProcessed",
                    dimensions_map={"Status": "FAILED", "Environment": self.env_name},
                    statistic="Sum",
                    label="Failed",
                ),
            ],
            width=12,
            height=6,
        )
        widgets.append(throughput_widget)

        # Idempotency metrics
        idempotency_widget = cloudwatch.GraphWidget(
            title="Idempotency Hit Rate",
            left=[
                cloudwatch.Metric(
                    namespace="IngestionPipeline",
                    metric_name="IdempotencyCheck",
                    dimensions_map={"Result": "HIT", "Environment": self.env_name},
                    statistic="Sum",
                    label="Cache Hit",
                ),
                cloudwatch.Metric(
                    namespace="IngestionPipeline",
                    metric_name="IdempotencyCheck",
                    dimensions_map={"Result": "MISS", "Environment": self.env_name},
                    statistic="Sum",
                    label="Cache Miss",
                ),
            ],
            width=12,
            height=6,
        )
        widgets.append(idempotency_widget)

        return widgets

    def _create_alarms(self) -> Dict[str, cloudwatch.Alarm]:
        """Create CloudWatch alarms"""
        alarms = {}

        # High error rate alarm
        alarms["high_error_rate"] = cloudwatch.Alarm(
            self,
            "HighErrorRateAlarm",
            alarm_name=f"ingestion-high-error-rate-{self.env_name}",
            alarm_description="High error rate in ingestion pipeline",
            metric=cloudwatch.MathExpression(
                expression="(errors / invocations) * 100",
                using_metrics={
                    "errors": cloudwatch.Metric(
                        namespace="AWS/Lambda",
                        metric_name="Errors",
                        dimensions_map={
                            "FunctionName": self.function_names["processor"]
                        },
                        statistic="Sum",
                    ),
                    "invocations": cloudwatch.Metric(
                        namespace="AWS/Lambda",
                        metric_name="Invocations",
                        dimensions_map={
                            "FunctionName": self.function_names["processor"]
                        },
                        statistic="Sum",
                    ),
                },
                label="Error Rate %",
            ),
            threshold=5.0,  # 5% error rate
            evaluation_periods=2,
            datapoints_to_alarm=2,
        )

        # DLQ depth alarm
        alarms["dlq_depth"] = cloudwatch.Alarm(
            self,
            "DLQDepthAlarm",
            alarm_name=f"ingestion-dlq-depth-{self.env_name}",
            alarm_description="Messages accumulating in DLQ",
            metric=cloudwatch.Metric(
                namespace="AWS/SQS",
                metric_name="ApproximateNumberOfMessages",
                dimensions_map={"QueueName": self.queue_names["dlq"]},
                statistic="Average",
            ),
            threshold=10,
            evaluation_periods=2,
            datapoints_to_alarm=1,
        )

        # Function duration alarm
        alarms["high_duration"] = cloudwatch.Alarm(
            self,
            "HighDurationAlarm",
            alarm_name=f"ingestion-high-duration-{self.env_name}",
            alarm_description="Function duration exceeding threshold",
            metric=cloudwatch.Metric(
                namespace="AWS/Lambda",
                metric_name="Duration",
                dimensions_map={"FunctionName": self.function_names["processor"]},
                statistic="Average",
            ),
            threshold=25000,  # 25 seconds
            evaluation_periods=3,
            datapoints_to_alarm=2,
        )

        # Old message alarm
        alarms["old_messages"] = cloudwatch.Alarm(
            self,
            "OldMessagesAlarm",
            alarm_name=f"ingestion-old-messages-{self.env_name}",
            alarm_description="Messages aging in queue",
            metric=cloudwatch.Metric(
                namespace="AWS/SQS",
                metric_name="ApproximateAgeOfOldestMessage",
                dimensions_map={"QueueName": self.queue_names["main_queue"]},
                statistic="Maximum",
            ),
            threshold=1800,  # 30 minutes
            evaluation_periods=2,
            datapoints_to_alarm=1,
        )

        # Add SNS actions to alarms
        for alarm in alarms.values():
            alarm.add_alarm_action(cw_actions.SnsAction(self.alert_topic))

        return alarms

    def _create_custom_metrics(self):
        """Create custom metric filters from logs"""

        # Error categorization metric filter
        for func_type, func_name in self.function_names.items():
            log_group = logs.LogGroup.from_log_group_name(
                self, f"{func_type}LogGroup", log_group_name=f"/aws/lambda/{func_name}"
            )

            # Error category metric filter
            logs.MetricFilter(
                self,
                f"{func_type}ErrorCategoryFilter",
                log_group=log_group,
                metric_namespace="IngestionPipeline",
                metric_name="ErrorCount",
                filter_pattern=logs.FilterPattern.literal(
                    '[timestamp, level="ERROR", logger, message]'
                ),
                metric_value="1",
                default_value=0,
                dimensions={
                    "FunctionType": func_type,
                    "Environment": self.env_name,
                },
            )

            # Duration metric filter
            logs.MetricFilter(
                self,
                f"{func_type}DurationFilter",
                log_group=log_group,
                metric_namespace="IngestionPipeline",
                metric_name="ProcessingDuration",
                filter_pattern=logs.FilterPattern.literal(
                    '[timestamp, level, logger, message="*durationMs*", durationMs]'
                ),
                metric_value="$durationMs",
                default_value=0,
                dimensions={
                    "FunctionType": func_type,
                    "Environment": self.env_name,
                },
            )

    def add_email_subscription(self, email: str):
        """Add email subscription to alert topic"""
        sns.Subscription(
            self,
            "EmailSubscription",
            topic=self.alert_topic,
            protocol=sns.SubscriptionProtocol.EMAIL,
            endpoint=email,
        )

    def add_slack_webhook(self, webhook_url: str):
        """Add Slack webhook subscription to alert topic"""
        sns.Subscription(
            self,
            "SlackSubscription",
            topic=self.alert_topic,
            protocol=sns.SubscriptionProtocol.HTTPS,
            endpoint=webhook_url,
        )
