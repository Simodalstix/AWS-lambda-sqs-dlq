"""
API Gateway Stack for the ingestion pipeline
"""

from aws_cdk import (
    Stack,
    Duration,
    aws_apigatewayv2 as apigwv2,
    aws_apigatewayv2_integrations as integrations,
    aws_logs as logs,
    aws_ssm as ssm,
    RemovalPolicy,
)
from constructs import Construct
from .functions_stack import FunctionsStack


class ApiStack(Stack):
    """
    Stack containing HTTP API Gateway v2 for the ingestion pipeline
    """

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        functions_stack: FunctionsStack,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Get context values
        env_name = self.node.try_get_context("envName") or "dev"
        auth_mode = self.node.try_get_context("authMode") or "none"

        # Store functions stack reference
        self.functions_stack = functions_stack

        # Create access log group
        access_log_group = logs.LogGroup(
            self,
            "ApiAccessLogs",
            log_group_name=f"/aws/apigateway/ingestion-api-{env_name}",
            retention=(
                logs.RetentionDays.ONE_WEEK
                if env_name == "dev"
                else logs.RetentionDays.ONE_MONTH
            ),
            removal_policy=RemovalPolicy.DESTROY,
        )

        # Create HTTP API
        self.api = apigwv2.HttpApi(
            self,
            "IngestionApi",
            api_name=f"ingestion-api-{env_name}",
            description=f"Ingestion pipeline API - {env_name}",
            cors_preflight=apigwv2.CorsPreflightOptions(
                allow_origins=(
                    ["*"] if env_name == "dev" else ["https://yourdomain.com"]
                ),
                allow_methods=[
                    apigwv2.CorsHttpMethod.GET,
                    apigwv2.CorsHttpMethod.POST,
                    apigwv2.CorsHttpMethod.OPTIONS,
                ],
                allow_headers=[
                    "Content-Type",
                    "Authorization",
                    "X-Amz-Date",
                    "X-Api-Key",
                ],
                max_age=Duration.hours(1),
            ),
        )

        # Create default stage with access logging
        self.stage = apigwv2.HttpStage(
            self,
            "DefaultStage",
            http_api=self.api,
            stage_name="$default",
            auto_deploy=True,
            access_log_destination=apigwv2.HttpStageAccessLogDestination.cloud_watch_logs(
                access_log_group
            ),
            access_log_format=apigwv2.AccessLogFormat.json_with_standard_fields(
                request_id=True,
                request_time=True,
                request_time_epoch=True,
                response_length=True,
                status=True,
                error_message=True,
                error_response_type=True,
            ),
            throttle=apigwv2.ThrottleSettings(
                rate_limit=1000,  # requests per second
                burst_limit=2000,  # burst capacity
            ),
        )

        # Create Lambda integrations
        ingest_integration = integrations.HttpLambdaIntegration(
            "IngestIntegration",
            functions_stack.ingest_function.function,
            payload_format_version=apigwv2.PayloadFormatVersion.VERSION_2_0,
        )

        redrive_integration = integrations.HttpLambdaIntegration(
            "RedriveIntegration",
            functions_stack.redrive_function.function,
            payload_format_version=apigwv2.PayloadFormatVersion.VERSION_2_0,
        )

        # Add routes
        self.api.add_routes(
            path="/events",
            methods=[apigwv2.HttpMethod.POST],
            integration=ingest_integration,
        )

        self.api.add_routes(
            path="/redrive/start",
            methods=[apigwv2.HttpMethod.POST],
            integration=redrive_integration,
        )

        self.api.add_routes(
            path="/redrive/preview",
            methods=[apigwv2.HttpMethod.GET],
            integration=redrive_integration,
        )

        self.api.add_routes(
            path="/redrive/cancel",
            methods=[apigwv2.HttpMethod.POST],
            integration=redrive_integration,
        )

        # Add health check endpoint
        health_integration = integrations.HttpLambdaIntegration(
            "HealthIntegration",
            functions_stack.ingest_function.function,  # Reuse ingest function for health
            payload_format_version=apigwv2.PayloadFormatVersion.VERSION_2_0,
        )

        self.api.add_routes(
            path="/health",
            methods=[apigwv2.HttpMethod.GET],
            integration=health_integration,
        )

        # Grant API Gateway permission to invoke Lambda functions
        from aws_cdk import aws_iam as iam
        
        functions_stack.ingest_function.function.grant_invoke(
            iam.ServicePrincipal("apigateway.amazonaws.com")
        )

        functions_stack.redrive_function.function.grant_invoke(
            iam.ServicePrincipal("apigateway.amazonaws.com")
        )

        # Store API URL for outputs
        self.api_url = self.api.api_endpoint
        self.api_id = self.api.api_id

        # Create SSM parameter for API URL
        ssm.StringParameter(
            self,
            "ApiUrlParameter",
            parameter_name="/ingestion/api_url",
            string_value=self.api_url,
            description="API Gateway endpoint URL",
        )

    def add_authorizer(self, authorizer_name: str, authorizer_type: str = "JWT"):
        """Add an authorizer to the API (placeholder for future auth implementation)"""
        # This would be implemented based on specific auth requirements
        # For now, we're using "none" auth mode as specified in context
        pass
