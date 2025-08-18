"""
Lambda function construct with observability and security best practices
"""

from aws_cdk import (
    aws_lambda as lambda_,
    aws_iam as iam,
    aws_logs as logs,
    aws_kms as kms,
    Duration,
    RemovalPolicy,
)
from constructs import Construct
from typing import Optional, Dict, List


class ObservableLambda(Construct):
    """
    Lambda function with built-in observability, security, and operational best practices
    """

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        function_name: str,
        handler: str,
        code_path: str,
        timeout: Duration,
        environment_variables: Optional[Dict[str, str]] = None,
        encryption_key: Optional[kms.IKey] = None,
        reserved_concurrency: Optional[int] = None,
        memory_size: int = 128,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Get context values
        env_name = self.node.try_get_context("envName") or "dev"

        # Create log group with retention and encryption
        log_group = logs.LogGroup(
            self,
            "LogGroup",
            log_group_name=f"/aws/lambda/{function_name}",
            retention=(
                logs.RetentionDays.ONE_WEEK
                if env_name == "dev"
                else logs.RetentionDays.ONE_MONTH
            ),
            encryption_key=encryption_key,
            removal_policy=RemovalPolicy.DESTROY,
        )

        # Default environment variables
        default_env_vars = {
            "LOG_LEVEL": "INFO",
            "POWERTOOLS_SERVICE_NAME": function_name,
            "POWERTOOLS_METRICS_NAMESPACE": "IngestionLab",
            "POWERTOOLS_LOGGER_LOG_EVENT": "true" if env_name == "dev" else "false",
        }

        # Merge with provided environment variables
        final_env_vars = {**default_env_vars, **(environment_variables or {})}

        # Create Lambda function
        self.function = lambda_.Function(
            self,
            "Function",
            function_name=function_name,
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler=handler,
            code=lambda_.Code.from_asset(code_path),
            timeout=timeout,
            memory_size=memory_size,
            environment=final_env_vars,
            log_group=log_group,
            reserved_concurrent_executions=reserved_concurrency,
            # Enable tracing for X-Ray
            tracing=lambda_.Tracing.ACTIVE,
            # Enable insights for better observability
            insights_version=lambda_.LambdaInsightsVersion.VERSION_1_0_229_0,
            # Security best practices
            environment_encryption=encryption_key,
            # Architecture
            architecture=lambda_.Architecture.ARM_64,  # Better price/performance
        )

        # Add basic execution role permissions
        self.function.add_to_role_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["xray:PutTraceSegments", "xray:PutTelemetryRecords"],
                resources=["*"],
            )
        )

        # Store references
        self.log_group = log_group
        self.function_name = function_name
        self.function_arn = self.function.function_arn

    def add_environment_variable(self, key: str, value: str) -> None:
        """Add an environment variable to the function"""
        self.function.add_environment(key, value)

    def add_policy_statement(self, statement: iam.PolicyStatement) -> None:
        """Add a policy statement to the function's execution role"""
        self.function.add_to_role_policy(statement)

    def grant_invoke(self, grantee) -> iam.Grant:
        """Grant invoke permissions to the function"""
        return self.function.grant_invoke(grantee)

    def add_event_source(self, source) -> None:
        """Add an event source to the function"""
        self.function.add_event_source(source)

    def create_alias(self, alias_name: str, version: lambda_.IVersion) -> lambda_.Alias:
        """Create an alias for the function"""
        return lambda_.Alias(
            self, f"Alias{alias_name}", alias_name=alias_name, version=version
        )

    def create_metric_filter(
        self,
        filter_name: str,
        filter_pattern: str,
        metric_name: str,
        metric_namespace: str = "IngestionLab/Lambda",
        default_value: float = 0,
    ) -> logs.MetricFilter:
        """Create a metric filter on the function's log group"""
        return logs.MetricFilter(
            self,
            f"MetricFilter{filter_name}",
            log_group=self.log_group,
            metric_namespace=metric_namespace,
            metric_name=metric_name,
            filter_pattern=logs.FilterPattern.literal(filter_pattern),
            default_value=default_value,
        )

    @property
    def role(self) -> iam.IRole:
        """Return the function's execution role"""
        return self.function.role
