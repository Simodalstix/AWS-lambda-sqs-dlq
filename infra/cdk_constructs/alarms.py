"""
CloudWatch Alarms construct for ingestion pipeline monitoring
"""

from aws_cdk import (
    aws_cloudwatch as cloudwatch,
    aws_cloudwatch_actions as cloudwatch_actions,
    aws_sns as sns,
    aws_sqs as sqs,
    aws_lambda as lambda_,
    aws_apigatewayv2 as apigwv2,
    Duration,
)
from constructs import Construct
from typing import List, Optional


class IngestionAlarms(Construct):
    """
    CloudWatch alarms for monitoring the ingestion pipeline with SNS notifications
    """

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        main_queue: sqs.Queue,
        dlq: sqs.Queue,
        lambda_functions: dict,
        api: apigwv2.HttpApi,
        notification_topic: sns.Topic,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Store references
        self.notification_topic = notification_topic
        self.alarms = []

        # Create alarm actions
        self.alarm_action = cloudwatch_actions.SnsAction(notification_topic)
        self.ok_action = cloudwatch_actions.SnsAction(notification_topic)

        # Create alarms
        self._create_queue_alarms(main_queue, dlq)
        self._create_lambda_alarms(lambda_functions)
        self._create_api_alarms(api)
        self._create_custom_metric_alarms()

    def _create_queue_alarms(self, main_queue: sqs.Queue, dlq: sqs.Queue):
        """Create SQS queue-related alarms"""

        # DLQ depth alarm - critical
        dlq_depth_alarm = cloudwatch.Alarm(
            self,
            "DlqDepthAlarm",
            alarm_name="IngestionLab-DLQ-Depth",
            alarm_description="DLQ has messages - indicates processing failures",
            metric=dlq.metric_approximate_number_of_messages_visible(
                period=Duration.minutes(1)
            ),
            threshold=1,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
            evaluation_periods=2,
            datapoints_to_alarm=2,
            treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING,
        )
        dlq_depth_alarm.add_alarm_action(self.alarm_action)
        dlq_depth_alarm.add_ok_action(self.ok_action)
        self.alarms.append(dlq_depth_alarm)

        # DLQ age alarm - critical
        dlq_age_alarm = cloudwatch.Alarm(
            self,
            "DlqAgeAlarm",
            alarm_name="IngestionLab-DLQ-Age",
            alarm_description="Messages in DLQ are aging - manual intervention needed",
            metric=dlq.metric_approximate_age_of_oldest_message(
                period=Duration.minutes(1)
            ),
            threshold=300,  # 5 minutes
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_THRESHOLD,
            evaluation_periods=3,
            datapoints_to_alarm=2,
            treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING,
        )
        dlq_age_alarm.add_alarm_action(self.alarm_action)
        dlq_age_alarm.add_ok_action(self.ok_action)
        self.alarms.append(dlq_age_alarm)

        # Main queue backlog alarm - warning
        main_queue_backlog_alarm = cloudwatch.Alarm(
            self,
            "MainQueueBacklogAlarm",
            alarm_name="IngestionLab-MainQueue-Backlog",
            alarm_description="Main queue has significant backlog",
            metric=main_queue.metric_approximate_number_of_messages_visible(
                period=Duration.minutes(5)
            ),
            threshold=100,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_THRESHOLD,
            evaluation_periods=2,
            datapoints_to_alarm=2,
            treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING,
        )
        main_queue_backlog_alarm.add_alarm_action(self.alarm_action)
        main_queue_backlog_alarm.add_ok_action(self.ok_action)
        self.alarms.append(main_queue_backlog_alarm)

        # Main queue age alarm - warning
        main_queue_age_alarm = cloudwatch.Alarm(
            self,
            "MainQueueAgeAlarm",
            alarm_name="IngestionLab-MainQueue-Age",
            alarm_description="Messages in main queue are aging",
            metric=main_queue.metric_approximate_age_of_oldest_message(
                period=Duration.minutes(5)
            ),
            threshold=600,  # 10 minutes
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_THRESHOLD,
            evaluation_periods=2,
            datapoints_to_alarm=2,
            treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING,
        )
        main_queue_age_alarm.add_alarm_action(self.alarm_action)
        main_queue_age_alarm.add_ok_action(self.ok_action)
        self.alarms.append(main_queue_age_alarm)

    def _create_lambda_alarms(self, lambda_functions: dict):
        """Create Lambda function-related alarms"""

        # Worker function errors - critical
        worker_errors_alarm = cloudwatch.Alarm(
            self,
            "WorkerErrorsAlarm",
            alarm_name="IngestionLab-Worker-Errors",
            alarm_description="Worker function is experiencing errors",
            metric=lambda_functions["worker"].metric_errors(period=Duration.minutes(5)),
            threshold=1,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
            evaluation_periods=1,
            datapoints_to_alarm=1,
            treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING,
        )
        worker_errors_alarm.add_alarm_action(self.alarm_action)
        worker_errors_alarm.add_ok_action(self.ok_action)
        self.alarms.append(worker_errors_alarm)

        # Ingest function errors - critical
        ingest_errors_alarm = cloudwatch.Alarm(
            self,
            "IngestErrorsAlarm",
            alarm_name="IngestionLab-Ingest-Errors",
            alarm_description="Ingest function is experiencing errors",
            metric=lambda_functions["ingest"].metric_errors(period=Duration.minutes(5)),
            threshold=5,  # Allow some errors for ingest
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_THRESHOLD,
            evaluation_periods=2,
            datapoints_to_alarm=2,
            treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING,
        )
        ingest_errors_alarm.add_alarm_action(self.alarm_action)
        ingest_errors_alarm.add_ok_action(self.ok_action)
        self.alarms.append(ingest_errors_alarm)

        # Worker function throttles - warning
        worker_throttles_alarm = cloudwatch.Alarm(
            self,
            "WorkerThrottlesAlarm",
            alarm_name="IngestionLab-Worker-Throttles",
            alarm_description="Worker function is being throttled",
            metric=lambda_functions["worker"].metric_throttles(
                period=Duration.minutes(5)
            ),
            threshold=1,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
            evaluation_periods=1,
            datapoints_to_alarm=1,
            treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING,
        )
        worker_throttles_alarm.add_alarm_action(self.alarm_action)
        worker_throttles_alarm.add_ok_action(self.ok_action)
        self.alarms.append(worker_throttles_alarm)

        # Ingest function throttles - warning
        ingest_throttles_alarm = cloudwatch.Alarm(
            self,
            "IngestThrottlesAlarm",
            alarm_name="IngestionLab-Ingest-Throttles",
            alarm_description="Ingest function is being throttled",
            metric=lambda_functions["ingest"].metric_throttles(
                period=Duration.minutes(5)
            ),
            threshold=1,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
            evaluation_periods=1,
            datapoints_to_alarm=1,
            treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING,
        )
        ingest_throttles_alarm.add_alarm_action(self.alarm_action)
        ingest_throttles_alarm.add_ok_action(self.ok_action)
        self.alarms.append(ingest_throttles_alarm)

        # Worker function duration - warning
        worker_duration_alarm = cloudwatch.Alarm(
            self,
            "WorkerDurationAlarm",
            alarm_name="IngestionLab-Worker-Duration",
            alarm_description="Worker function duration is high",
            metric=lambda_functions["worker"].metric_duration(
                statistic="Average", period=Duration.minutes(5)
            ),
            threshold=25000,  # 25 seconds (close to 30s timeout)
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_THRESHOLD,
            evaluation_periods=3,
            datapoints_to_alarm=2,
            treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING,
        )
        worker_duration_alarm.add_alarm_action(self.alarm_action)
        worker_duration_alarm.add_ok_action(self.ok_action)
        self.alarms.append(worker_duration_alarm)

        # Iterator age alarm for SQS event source
        iterator_age_alarm = cloudwatch.Alarm(
            self,
            "IteratorAgeAlarm",
            alarm_name="IngestionLab-Iterator-Age",
            alarm_description="SQS iterator age is high - indicates processing delays",
            metric=cloudwatch.Metric(
                namespace="AWS/Lambda",
                metric_name="IteratorAge",
                dimensions_map={
                    "FunctionName": lambda_functions["worker"].function_name
                },
                statistic="Maximum",
                period=Duration.minutes(5),
            ),
            threshold=60000,  # 1 minute in milliseconds
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_THRESHOLD,
            evaluation_periods=2,
            datapoints_to_alarm=2,
            treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING,
        )
        iterator_age_alarm.add_alarm_action(self.alarm_action)
        iterator_age_alarm.add_ok_action(self.ok_action)
        self.alarms.append(iterator_age_alarm)

    def _create_api_alarms(self, api: apigwv2.HttpApi):
        """Create API Gateway-related alarms"""

        # API 5XX errors - critical
        api_5xx_alarm = cloudwatch.Alarm(
            self,
            "Api5xxAlarm",
            alarm_name="IngestionLab-API-5XX",
            alarm_description="API Gateway is returning 5XX errors",
            metric=cloudwatch.Metric(
                namespace="AWS/ApiGatewayV2",
                metric_name="5XXError",
                dimensions_map={"ApiId": api.api_id},
                statistic="Sum",
                period=Duration.minutes(5),
            ),
            threshold=5,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_THRESHOLD,
            evaluation_periods=2,
            datapoints_to_alarm=2,
            treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING,
        )
        api_5xx_alarm.add_alarm_action(self.alarm_action)
        api_5xx_alarm.add_ok_action(self.ok_action)
        self.alarms.append(api_5xx_alarm)

        # API 4XX errors - warning (high rate)
        api_4xx_alarm = cloudwatch.Alarm(
            self,
            "Api4xxAlarm",
            alarm_name="IngestionLab-API-4XX",
            alarm_description="API Gateway is returning high rate of 4XX errors",
            metric=cloudwatch.Metric(
                namespace="AWS/ApiGatewayV2",
                metric_name="4XXError",
                dimensions_map={"ApiId": api.api_id},
                statistic="Sum",
                period=Duration.minutes(5),
            ),
            threshold=20,  # Allow some 4XX errors but alert on high rates
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_THRESHOLD,
            evaluation_periods=2,
            datapoints_to_alarm=2,
            treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING,
        )
        api_4xx_alarm.add_alarm_action(self.alarm_action)
        api_4xx_alarm.add_ok_action(self.ok_action)
        self.alarms.append(api_4xx_alarm)

        # API latency - warning
        api_latency_alarm = cloudwatch.Alarm(
            self,
            "ApiLatencyAlarm",
            alarm_name="IngestionLab-API-Latency",
            alarm_description="API Gateway latency is high",
            metric=cloudwatch.Metric(
                namespace="AWS/ApiGatewayV2",
                metric_name="Latency",
                dimensions_map={"ApiId": api.api_id},
                statistic="Average",
                period=Duration.minutes(5),
            ),
            threshold=5000,  # 5 seconds
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_THRESHOLD,
            evaluation_periods=3,
            datapoints_to_alarm=2,
            treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING,
        )
        api_latency_alarm.add_alarm_action(self.alarm_action)
        api_latency_alarm.add_ok_action(self.ok_action)
        self.alarms.append(api_latency_alarm)

    def _create_custom_metric_alarms(self):
        """Create alarms for custom application metrics"""

        # High validation error rate
        validation_errors_alarm = cloudwatch.Alarm(
            self,
            "ValidationErrorsAlarm",
            alarm_name="IngestionLab-Validation-Errors",
            alarm_description="High rate of validation errors",
            metric=cloudwatch.Metric(
                namespace="IngestionLab/Ingest",
                metric_name="ValidationErrors",
                statistic="Sum",
                period=Duration.minutes(5),
            ),
            threshold=10,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_THRESHOLD,
            evaluation_periods=2,
            datapoints_to_alarm=2,
            treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING,
        )
        validation_errors_alarm.add_alarm_action(self.alarm_action)
        validation_errors_alarm.add_ok_action(self.ok_action)
        self.alarms.append(validation_errors_alarm)

        # Low processing rate (composite alarm)
        processing_rate_alarm = cloudwatch.Alarm(
            self,
            "ProcessingRateAlarm",
            alarm_name="IngestionLab-Low-Processing-Rate",
            alarm_description="Message processing rate is low",
            metric=cloudwatch.Metric(
                namespace="IngestionLab/Worker",
                metric_name="ProcessedMessages",
                statistic="Sum",
                period=Duration.minutes(10),
            ),
            threshold=1,
            comparison_operator=cloudwatch.ComparisonOperator.LESS_THAN_THRESHOLD,
            evaluation_periods=2,
            datapoints_to_alarm=2,
            treat_missing_data=cloudwatch.TreatMissingData.BREACHING,
        )
        processing_rate_alarm.add_alarm_action(self.alarm_action)
        processing_rate_alarm.add_ok_action(self.ok_action)
        self.alarms.append(processing_rate_alarm)

    def create_composite_alarm(
        self, alarm_name: str, alarm_rule: str, description: str
    ) -> cloudwatch.CompositeAlarm:
        """Create a composite alarm from multiple alarms"""
        composite_alarm = cloudwatch.CompositeAlarm(
            self,
            f"Composite{alarm_name}",
            composite_alarm_name=alarm_name,
            alarm_description=description,
            alarm_rule=cloudwatch.AlarmRule.from_string(alarm_rule),
        )
        composite_alarm.add_alarm_action(self.alarm_action)
        composite_alarm.add_ok_action(self.ok_action)
        return composite_alarm

    def get_alarm_names(self) -> List[str]:
        """Get list of all alarm names"""
        return [alarm.alarm_name for alarm in self.alarms]
