"""
API Gateway Stack for the ingestion pipeline
"""

from aws_cdk import (
    Stack,
    Duration,
    aws_apigatewayv2 as apigwv2,
    aws_apigatewayv2_integrations as integrations,
    aws_ssm as ssm,
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

        # Create HTTP API
        self.api = apigwv2.HttpApi(
            self,
            "IngestionApi",
            api_name=f"ingestion-api-{env_name}",
            description=f"Ingestion pipeline API - {env_name}",
            cors_preflight=apigwv2.CorsPreflightOptions(
                allow_origins=["*"] if env_name == "dev" else ["https://yourdomain.com"],
                allow_methods=[
                    apigwv2.CorsHttpMethod.GET,
                    apigwv2.CorsHttpMethod.POST,
                    apigwv2.CorsHttpMethod.OPTIONS,
                ],
                allow_headers=["Content-Type", "Authorization"],
                max_age=Duration.hours(1),
            ),
        )

        # Create Lambda integrations
        ingest_integration = integrations.HttpLambdaIntegration(
            "IngestIntegration",
            functions_stack.ingest_function.function,
        )
        redrive_integration = integrations.HttpLambdaIntegration(
            "RedriveIntegration", 
            functions_stack.redrive_function.function,
        )

        # Add routes
        self.api.add_routes(
            path="/events",
            methods=[apigwv2.HttpMethod.POST],
            integration=ingest_integration,
        )

        self.api.add_routes(
            path="/health",
            methods=[apigwv2.HttpMethod.GET],
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