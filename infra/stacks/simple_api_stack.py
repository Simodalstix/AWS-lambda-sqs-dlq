"""
Simple API Gateway Stack for the ingestion pipeline
"""

from aws_cdk import (
    Stack,
    aws_apigateway as apigw,
    aws_logs as logs,
    aws_ssm as ssm,
    RemovalPolicy,
)
from constructs import Construct
from .functions_stack import FunctionsStack


class ApiStack(Stack):
    """
    Stack containing REST API Gateway for the ingestion pipeline
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

        # Store functions stack reference
        self.functions_stack = functions_stack

        # Create REST API
        self.api = apigw.RestApi(
            self,
            "IngestionApi",
            rest_api_name=f"ingestion-api-{env_name}",
            description=f"Ingestion pipeline API - {env_name}",
            default_cors_preflight_options=apigw.CorsOptions(
                allow_origins=apigw.Cors.ALL_ORIGINS,
                allow_methods=apigw.Cors.ALL_METHODS,
                allow_headers=["Content-Type", "Authorization"],
            ),
        )

        # Create Lambda integrations
        ingest_integration = apigw.LambdaIntegration(
            functions_stack.ingest_function.function
        )
        redrive_integration = apigw.LambdaIntegration(
            functions_stack.redrive_function.function
        )

        # Add resources and methods
        events_resource = self.api.root.add_resource("events")
        events_resource.add_method("POST", ingest_integration)

        health_resource = self.api.root.add_resource("health")
        health_resource.add_method("GET", ingest_integration)

        redrive_resource = self.api.root.add_resource("redrive")
        redrive_start = redrive_resource.add_resource("start")
        redrive_start.add_method("POST", redrive_integration)

        redrive_preview = redrive_resource.add_resource("preview")
        redrive_preview.add_method("GET", redrive_integration)

        # Store API URL for outputs
        self.api_url = self.api.url
        self.api_id = self.api.rest_api_id

        # Create SSM parameter for API URL
        ssm.StringParameter(
            self,
            "ApiUrlParameter",
            parameter_name="/ingestion/api_url",
            string_value=self.api_url,
            description="API Gateway endpoint URL",
        )