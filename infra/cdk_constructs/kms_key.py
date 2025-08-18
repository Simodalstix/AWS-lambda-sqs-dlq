"""
KMS Key construct for encryption across the ingestion pipeline
"""

from aws_cdk import aws_kms as kms, aws_iam as iam, Duration, RemovalPolicy
from constructs import Construct


class IngestionKmsKey(Construct):
    """
    KMS key for encrypting SQS queues, DynamoDB table, and other resources
    """

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Get context values
        env_name = self.node.try_get_context("envName") or "dev"
        kms_alias = self.node.try_get_context("kmsAlias") or "alias/ingestion-lab"

        # Create KMS key for encryption
        self.key = kms.Key(
            self,
            "IngestionKey",
            description=f"KMS key for ingestion pipeline - {env_name}",
            enable_key_rotation=True,
            removal_policy=(
                RemovalPolicy.DESTROY if env_name == "dev" else RemovalPolicy.RETAIN
            ),
            policy=iam.PolicyDocument(
                statements=[
                    # Allow root account full access
                    iam.PolicyStatement(
                        sid="EnableRootAccess",
                        effect=iam.Effect.ALLOW,
                        principals=[iam.AccountRootPrincipal()],
                        actions=["kms:*"],
                        resources=["*"],
                    ),
                    # Allow CloudWatch Logs to use the key
                    iam.PolicyStatement(
                        sid="AllowCloudWatchLogs",
                        effect=iam.Effect.ALLOW,
                        principals=[
                            iam.ServicePrincipal(f"logs.{self.region}.amazonaws.com")
                        ],
                        actions=[
                            "kms:Encrypt",
                            "kms:Decrypt",
                            "kms:ReEncrypt*",
                            "kms:GenerateDataKey*",
                            "kms:DescribeKey",
                        ],
                        resources=["*"],
                    ),
                    # Allow SQS service to use the key
                    iam.PolicyStatement(
                        sid="AllowSQSService",
                        effect=iam.Effect.ALLOW,
                        principals=[iam.ServicePrincipal("sqs.amazonaws.com")],
                        actions=[
                            "kms:Encrypt",
                            "kms:Decrypt",
                            "kms:ReEncrypt*",
                            "kms:GenerateDataKey*",
                            "kms:DescribeKey",
                        ],
                        resources=["*"],
                    ),
                    # Allow DynamoDB service to use the key
                    iam.PolicyStatement(
                        sid="AllowDynamoDBService",
                        effect=iam.Effect.ALLOW,
                        principals=[iam.ServicePrincipal("dynamodb.amazonaws.com")],
                        actions=[
                            "kms:Encrypt",
                            "kms:Decrypt",
                            "kms:ReEncrypt*",
                            "kms:GenerateDataKey*",
                            "kms:DescribeKey",
                        ],
                        resources=["*"],
                    ),
                ]
            ),
        )

        # Create alias for the key
        self.alias = kms.Alias(
            self,
            "IngestionKeyAlias",
            alias_name=f"{kms_alias}-{env_name}",
            target_key=self.key,
        )

    @property
    def key_arn(self) -> str:
        """Return the KMS key ARN"""
        return self.key.key_arn

    @property
    def key_id(self) -> str:
        """Return the KMS key ID"""
        return self.key.key_id
