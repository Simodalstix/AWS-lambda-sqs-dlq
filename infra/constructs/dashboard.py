"""
CloudWatch Dashboard construct for ingestion pipeline observability
"""

from aws_cdk import (
    aws_cloudwatch as cloudwatch,
    aws_sqs as sqs,
    aws_lambda as lambda_,
    aws_apigatewayv2 as apigwv2,
    Duration,
)
from constructs import Construct
from typing import List


class IngestionDashboard(Construct):
    """
    CloudWatch dashboard for monitoring the ingestion pipeline
    """

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        dashboard_name: str,
        main_queue: sqs.Queue,
        dlq: sqs.Queue,
        lambda_functions: dict,
        api: apigwv2.HttpApi,
        event_bus_name: str,
        **kwargs
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Create dashboard
        self.dashboard = cloudwatch.Dashboard(
            self,
            "IngestionDashboard",
            dashboard_name=dashboard_name,
            period_override=cloudwatch.PeriodOverride.AUTO,
        )

        # Add widgets to dashboard
        self._add_overview_widgets(main_queue, dlq, lambda_functions, api)
        self._add_queue_widgets(main_queue, dlq)
        self._add_lambda_widgets(lambda_functions)
        self._add_api_widgets(api)
        self._add_eventbridge_widgets(event_bus_name)
        self._add_error_widgets(lambda_functions)

    def _add_overview_widgets(
        self,
        main_queue: sqs.Queue,
        dlq: sqs.Queue,
        lambda_functions: dict,
        api: apigwv2.HttpApi,
    ):
        """Add overview widgets"""

        # System health overview
        health_widget = cloudwatch.SingleValueWidget(
            title="System Health Overview",
            metrics=[
                # API Gateway requests
                cloudwatch.Metric(
                    namespace="AWS/ApiGatewayV2",
                    metric_name="Count",
                    dimensions_map={"ApiId": api.api_id},
                    statistic="Sum",
                    period=Duration.minutes(5),
                ),
                # Main queue depth
                main_queue.metric_approximate_number_of_messages_visible(
                    period=Duration.minutes(5)
                ),
                # DLQ depth
                dlq.metric_approximate_number_of_messages_visible(
                    period=Duration.minutes(5)
                ),
                # Lambda errors
                lambda_functions["worker"].metric_errors(period=Duration.minutes(5)),
            ],
            width=24,
            height=6,
        )

        self.dashboard.add_widgets(health_widget)

    def _add_queue_widgets(self, main_queue: sqs.Queue, dlq: sqs.Queue):
        """Add SQS queue monitoring widgets"""

        # Queue depths
        queue_depth_widget = cloudwatch.GraphWidget(
            title="Queue Depths",
            left=[
                main_queue.metric_approximate_number_of_messages_visible(
                    label="Main Queue - Visible Messages"
                ),
                main_queue.metric_approximate_number_of_messages_not_visible(
                    label="Main Queue - In Flight Messages"
                ),
                dlq.metric_approximate_number_of_messages_visible(
                    label="DLQ - Messages"
                ),
            ],
            width=12,
            height=6,
        )

        # Queue age metrics
        queue_age_widget = cloudwatch.GraphWidget(
            title="Message Age",
            left=[
                main_queue.metric_approximate_age_of_oldest_message(
                    label="Main Queue - Oldest Message Age"
                ),
                dlq.metric_approximate_age_of_oldest_message(
                    label="DLQ - Oldest Message Age"
                ),
            ],
            width=12,
            height=6,
        )

        self.dashboard.add_widgets(queue_depth_widget, queue_age_widget)

        # Queue throughput
        throughput_widget = cloudwatch.GraphWidget(
            title="Queue Throughput",
            left=[
                cloudwatch.Metric(
                    namespace="AWS/SQS",
                    metric_name="NumberOfMessagesSent",
                    dimensions_map={"QueueName": main_queue.queue_name},
                    statistic="Sum",
                    label="Messages Sent",
                ),
                cloudwatch.Metric(
                    namespace="AWS/SQS",
                    metric_name="NumberOfMessagesReceived",
                    dimensions_map={"QueueName": main_queue.queue_name},
                    statistic="Sum",
                    label="Messages Received",
                ),
                cloudwatch.Metric(
                    namespace="AWS/SQS",
                    metric_name="NumberOfMessagesDeleted",
                    dimensions_map={"QueueName": main_queue.queue_name},
                    statistic="Sum",
                    label="Messages Deleted",
                ),
            ],
            width=24,
            height=6,
        )

        self.dashboard.add_widgets(throughput_widget)

    def _add_lambda_widgets(self, lambda_functions: dict):
        """Add Lambda function monitoring widgets"""

        # Lambda invocations
        invocations_widget = cloudwatch.GraphWidget(
            title="Lambda Invocations",
            left=[
                lambda_functions["ingest"].metric_invocations(label="Ingest"),
                lambda_functions["worker"].metric_invocations(label="Worker"),
                lambda_functions["redrive"].metric_invocations(label="Redrive"),
            ],
            width=8,
            height=6,
        )

        # Lambda errors
        errors_widget = cloudwatch.GraphWidget(
            title="Lambda Errors",
            left=[
                lambda_functions["ingest"].metric_errors(label="Ingest Errors"),
                lambda_functions["worker"].metric_errors(label="Worker Errors"),
                lambda_functions["redrive"].metric_errors(label="Redrive Errors"),
            ],
            width=8,
            height=6,
        )

        # Lambda duration
        duration_widget = cloudwatch.GraphWidget(
            title="Lambda Duration (P95)",
            left=[
                lambda_functions["ingest"].metric_duration(
                    statistic="p95", label="Ingest P95"
                ),
                lambda_functions["worker"].metric_duration(
                    statistic="p95", label="Worker P95"
                ),
                lambda_functions["redrive"].metric_duration(
                    statistic="p95", label="Redrive P95"
                ),
            ],
            width=8,
            height=6,
        )

        self.dashboard.add_widgets(invocations_widget, errors_widget, duration_widget)

        # Lambda throttles
        throttles_widget = cloudwatch.GraphWidget(
            title="Lambda Throttles",
            left=[
                lambda_functions["ingest"].metric_throttles(label="Ingest Throttles"),
                lambda_functions["worker"].metric_throttles(label="Worker Throttles"),
                lambda_functions["redrive"].metric_throttles(label="Redrive Throttles"),
            ],
            width=12,
            height=6,
        )

        # Lambda concurrent executions
        concurrency_widget = cloudwatch.GraphWidget(
            title="Lambda Concurrent Executions",
            left=[
                cloudwatch.Metric(
                    namespace="AWS/Lambda",
                    metric_name="ConcurrentExecutions",
                    dimensions_map={
                        "FunctionName": lambda_functions["worker"].function_name
                    },
                    statistic="Maximum",
                    label="Worker Concurrency",
                )
            ],
            width=12,
            height=6,
        )

        self.dashboard.add_widgets(throttles_widget, concurrency_widget)

    def _add_api_widgets(self, api: apigwv2.HttpApi):
        """Add API Gateway monitoring widgets"""

        # API requests
        api_requests_widget = cloudwatch.GraphWidget(
            title="API Gateway Requests",
            left=[
                cloudwatch.Metric(
                    namespace="AWS/ApiGatewayV2",
                    metric_name="Count",
                    dimensions_map={"ApiId": api.api_id},
                    statistic="Sum",
                    label="Total Requests",
                )
            ],
            width=8,
            height=6,
        )

        # API latency
        api_latency_widget = cloudwatch.GraphWidget(
            title="API Gateway Latency",
            left=[
                cloudwatch.Metric(
                    namespace="AWS/ApiGatewayV2",
                    metric_name="IntegrationLatency",
                    dimensions_map={"ApiId": api.api_id},
                    statistic="Average",
                    label="Integration Latency",
                ),
                cloudwatch.Metric(
                    namespace="AWS/ApiGatewayV2",
                    metric_name="Latency",
                    dimensions_map={"ApiId": api.api_id},
                    statistic="Average",
                    label="Total Latency",
                ),
            ],
            width=8,
            height=6,
        )

        # API errors
        api_errors_widget = cloudwatch.GraphWidget(
            title="API Gateway Errors",
            left=[
                cloudwatch.Metric(
                    namespace="AWS/ApiGatewayV2",
                    metric_name="4XXError",
                    dimensions_map={"ApiId": api.api_id},
                    statistic="Sum",
                    label="4XX Errors",
                ),
                cloudwatch.Metric(
                    namespace="AWS/ApiGatewayV2",
                    metric_name="5XXError",
                    dimensions_map={"ApiId": api.api_id},
                    statistic="Sum",
                    label="5XX Errors",
                ),
            ],
            width=8,
            height=6,
        )

        self.dashboard.add_widgets(
            api_requests_widget, api_latency_widget, api_errors_widget
        )

    def _add_eventbridge_widgets(self, event_bus_name: str):
        """Add EventBridge monitoring widgets"""

        # EventBridge events
        events_widget = cloudwatch.GraphWidget(
            title="EventBridge Events",
            left=[
                cloudwatch.Metric(
                    namespace="AWS/Events",
                    metric_name="MatchedEvents",
                    dimensions_map={"EventBusName": event_bus_name},
                    statistic="Sum",
                    label="Matched Events",
                ),
                cloudwatch.Metric(
                    namespace="AWS/Events",
                    metric_name="SuccessfulInvocations",
                    dimensions_map={"EventBusName": event_bus_name},
                    statistic="Sum",
                    label="Successful Invocations",
                ),
                cloudwatch.Metric(
                    namespace="AWS/Events",
                    metric_name="FailedInvocations",
                    dimensions_map={"EventBusName": event_bus_name},
                    statistic="Sum",
                    label="Failed Invocations",
                ),
            ],
            width=24,
            height=6,
        )

        self.dashboard.add_widgets(events_widget)

    def _add_error_widgets(self, lambda_functions: dict):
        """Add custom error tracking widgets"""

        # Custom metrics from log filters
        custom_metrics_widget = cloudwatch.GraphWidget(
            title="Custom Application Metrics",
            left=[
                cloudwatch.Metric(
                    namespace="IngestionLab/Worker",
                    metric_name="ProcessedMessages",
                    statistic="Sum",
                    label="Processed Messages",
                ),
                cloudwatch.Metric(
                    namespace="IngestionLab/Worker",
                    metric_name="IdempotentMessages",
                    statistic="Sum",
                    label="Idempotent Messages",
                ),
                cloudwatch.Metric(
                    namespace="IngestionLab/Ingest",
                    metric_name="ValidationErrors",
                    statistic="Sum",
                    label="Validation Errors",
                ),
                cloudwatch.Metric(
                    namespace="IngestionLab/Redrive",
                    metric_name="RedrivenMessages",
                    statistic="Sum",
                    label="Redriven Messages",
                ),
            ],
            width=24,
            height=6,
        )

        self.dashboard.add_widgets(custom_metrics_widget)
