"""
Observability Stack for the ingestion pipeline
"""

from aws_cdk import Stack, aws_cloudwatch as cloudwatch, aws_logs as logs, RemovalPolicy
from constructs import Construct
from cdk_constructs.dashboard import IngestionDashboard
from cdk_constructs.alarms import IngestionAlarms
from .queue_stack import QueueStack
from .functions_stack import FunctionsStack
from .api_stack import ApiStack


class ObservabilityStack(Stack):
    """
    Stack containing CloudWatch dashboards, alarms, and observability components
    """

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        queue_stack: QueueStack,
        functions_stack: FunctionsStack,
        api_stack: ApiStack,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Get context values
        env_name = self.node.try_get_context("envName") or "dev"

        # Store stack references
        self.queue_stack = queue_stack
        self.functions_stack = functions_stack
        self.api_stack = api_stack

        # Create CloudWatch dashboard
        self.dashboard = IngestionDashboard(
            self,
            "Dashboard",
            dashboard_name=f"IngestionLab-{env_name}",
            main_queue=queue_stack.queue,
            dlq=queue_stack.dlq,
            lambda_functions=functions_stack.functions,
            api=api_stack.api,
            event_bus_name=queue_stack.event_bus.bus_name,
        )

        # Create CloudWatch alarms
        self.alarms = IngestionAlarms(
            self,
            "Alarms",
            main_queue=queue_stack.queue,
            dlq=queue_stack.dlq,
            lambda_functions=functions_stack.functions,
            api=api_stack.api,
            notification_topic=queue_stack.event_bus.notification_topic,
        )

        # Create composite alarms for system health
        self._create_composite_alarms()

        # Log insights queries disabled - CDK v2.150.0 API change
        # Can be added post-deployment via AWS Console
        # self._create_log_insights_queries()

        # Store references for outputs
        self.dashboard_url = f"https://console.aws.amazon.com/cloudwatch/home?region={self.region}#dashboards:name={self.dashboard.dashboard.dashboard_name}"
        self.alarm_names = self.alarms.get_alarm_names()

    def _create_composite_alarms(self):
        """Create composite alarms for overall system health"""

        # Critical system health alarm
        critical_alarm = self.alarms.create_composite_alarm(
            alarm_name=f"IngestionLab-Critical-{self.node.try_get_context('envName') or 'dev'}",
            alarm_rule=(
                "ALARM(IngestionLab-DLQ-Depth) OR "
                "ALARM(IngestionLab-DLQ-Age) OR "
                "ALARM(IngestionLab-Worker-Errors) OR "
                "ALARM(IngestionLab-API-5XX)"
            ),
            description="Critical issues detected in ingestion pipeline",
        )

        # Warning system health alarm
        warning_alarm = self.alarms.create_composite_alarm(
            alarm_name=f"IngestionLab-Warning-{self.node.try_get_context('envName') or 'dev'}",
            alarm_rule=(
                "ALARM(IngestionLab-MainQueue-Backlog) OR "
                "ALARM(IngestionLab-Worker-Throttles) OR "
                "ALARM(IngestionLab-API-Latency) OR "
                "ALARM(IngestionLab-Validation-Errors)"
            ),
            description="Warning conditions detected in ingestion pipeline",
        )

        self.critical_alarm = critical_alarm
        self.warning_alarm = warning_alarm

    def _create_log_insights_queries(self):
        """Create CloudWatch Logs Insights queries for troubleshooting"""

        # Query for error analysis
        error_query = logs.QueryDefinition(
            self,
            "ErrorAnalysisQuery",
            query_definition_name="IngestionLab-ErrorAnalysis",
            query_string="fields @timestamp, @message, requestId, errorType, idempotencyKey | filter @message like /ERROR/ | sort @timestamp desc | limit 100",
            log_groups=[
                self.functions_stack.ingest_function.log_group,
                self.functions_stack.worker_function.log_group,
                self.functions_stack.redrive_function.log_group,
            ],
        )

        # Query for performance analysis
        performance_query = logs.QueryDefinition(
            self,
            "PerformanceAnalysisQuery",
            query_definition_name="IngestionLab-PerformanceAnalysis",
            query_string="""
fields @timestamp, @message, requestId, durationMs, idempotencyKey
| filter @message like /processed/
| stats avg(durationMs), max(durationMs), min(durationMs), count() by bin(5m)
| sort @timestamp desc
            """.strip(),
            log_groups=[self.functions_stack.worker_function.log_group],
        )

        # Query for idempotency analysis
        idempotency_query = logs.QueryDefinition(
            self,
            "IdempotencyAnalysisQuery",
            query_definition_name="IngestionLab-IdempotencyAnalysis",
            query_string="""
fields @timestamp, @message, requestId, idempotencyKey, idempotent
| filter @message like /Idempotent message/
| stats count() by idempotencyKey
| sort count desc
| limit 50
            """.strip(),
            log_groups=[self.functions_stack.worker_function.log_group],
        )

        # Query for failure mode analysis
        failure_mode_query = logs.QueryDefinition(
            self,
            "FailureModeAnalysisQuery",
            query_definition_name="IngestionLab-FailureModeAnalysis",
            query_string="""
fields @timestamp, @message, requestId, failureMode, errorType
| filter @message like /Simulated/
| stats count() by failureMode, errorType
| sort count desc
            """.strip(),
            log_groups=[
                self.functions_stack.ingest_function.log_group,
                self.functions_stack.worker_function.log_group,
            ],
        )

        # Query for redrive operations
        redrive_query = logs.QueryDefinition(
            self,
            "RedriveAnalysisQuery",
            query_definition_name="IngestionLab-RedriveAnalysis",
            query_string="""
fields @timestamp, @message, requestId, count, processed, redriven
| filter @message like /redrive/
| sort @timestamp desc
| limit 100
            """.strip(),
            log_groups=[self.functions_stack.redrive_function.log_group],
        )

        # Store query references
        self.log_queries = {
            "error_analysis": error_query,
            "performance_analysis": performance_query,
            "idempotency_analysis": idempotency_query,
            "failure_mode_analysis": failure_mode_query,
            "redrive_analysis": redrive_query,
        }

    def add_custom_widget(self, widget: cloudwatch.IWidget):
        """Add a custom widget to the dashboard"""
        self.dashboard.dashboard.add_widgets(widget)

    def create_custom_alarm(
        self,
        alarm_id: str,
        alarm_name: str,
        metric: cloudwatch.Metric,
        threshold: float,
        comparison_operator: cloudwatch.ComparisonOperator,
        evaluation_periods: int = 2,
        datapoints_to_alarm: int = 2,
    ) -> cloudwatch.Alarm:
        """Create a custom alarm and add it to the notification system"""

        alarm = cloudwatch.Alarm(
            self,
            alarm_id,
            alarm_name=alarm_name,
            metric=metric,
            threshold=threshold,
            comparison_operator=comparison_operator,
            evaluation_periods=evaluation_periods,
            datapoints_to_alarm=datapoints_to_alarm,
            treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING,
        )

        # Add to notification system
        alarm.add_alarm_action(self.alarms.alarm_action)
        alarm.add_ok_action(self.alarms.ok_action)

        return alarm
