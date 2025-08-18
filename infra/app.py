#!/usr/bin/env python3
"""
Event-Driven Ingestion + DLQ Reliability Lab
Main CDK application entry point
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

import aws_cdk as cdk
from stacks.api_stack import ApiStack
from stacks.queue_stack import QueueStack
from stacks.functions_stack import FunctionsStack
from stacks.observability_stack import ObservabilityStack


def main():
    app = cdk.App()

    # Get context values with defaults
    env_name = app.node.try_get_context("envName") or "dev"
    account = app.node.try_get_context("account") or None
    region = app.node.try_get_context("region") or None

    env = cdk.Environment(account=account, region=region)

    # Stack naming convention
    stack_prefix = f"ingestion-lab-{env_name}"

    # Core infrastructure stacks
    queue_stack = QueueStack(
        app,
        f"{stack_prefix}-queues",
        env=env,
        description="SQS queues with DLQ for ingestion pipeline",
    )

    functions_stack = FunctionsStack(
        app,
        f"{stack_prefix}-functions",
        queue_stack=queue_stack,
        env=env,
        description="Lambda functions for ingestion pipeline",
    )

    api_stack = ApiStack(
        app,
        f"{stack_prefix}-api",
        functions_stack=functions_stack,
        env=env,
        description="API Gateway for ingestion pipeline",
    )

    observability_stack = ObservabilityStack(
        app,
        f"{stack_prefix}-observability",
        queue_stack=queue_stack,
        functions_stack=functions_stack,
        api_stack=api_stack,
        env=env,
        description="CloudWatch dashboards and alarms",
    )

    # Add dependencies
    functions_stack.add_dependency(queue_stack)
    api_stack.add_dependency(functions_stack)
    observability_stack.add_dependency(functions_stack)

    # Add tags to all stacks
    for stack in [queue_stack, functions_stack, api_stack, observability_stack]:
        cdk.Tags.of(stack).add("Project", "IngestionLab")
        cdk.Tags.of(stack).add("Environment", env_name)
        cdk.Tags.of(stack).add("Owner", "DevOps")

    app.synth()


if __name__ == "__main__":
    main()
