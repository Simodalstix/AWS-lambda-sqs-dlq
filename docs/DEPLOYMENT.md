# Deployment Guide

## Prerequisites

### Required Tools
- **AWS CLI** v2.x configured with deployment permissions
- **Python** 3.11+ 
- **Node.js** 20+ (for CDK CLI)
- **Poetry** (recommended) or pip

### AWS Permissions Required
Your AWS credentials need the following permissions:
- CloudFormation full access
- Lambda full access
- SQS full access
- DynamoDB full access
- API Gateway full access
- CloudWatch full access
- IAM role creation and attachment
- EventBridge full access
- SNS full access
- SSM Parameter Store access

## Environment Setup

```bash
# Clone repository
git clone https://github.com/username/AWS-lambda-sqs-dlq.git
cd AWS-lambda-sqs-dlq

# Install dependencies
poetry install
# OR: python -m venv .venv && source .venv/bin/activate && pip install -r infra/requirements.txt

# Install CDK CLI
npm install -g aws-cdk@2.150.0
```

## Configuration

Edit `infra/cdk.json` to customize:

```json
{
  "context": {
    "envName": "dev",                    // Environment name
    "alarmEmail": "your-email@domain.com", // Your email for alerts
    "useKmsCmk": false,                  // Enable customer-managed KMS
    "maxReceiveCount": 5,                // DLQ threshold
    "workerTimeoutSeconds": 30           // Lambda timeout
  }
}
```

## Deployment Steps

### 1. Bootstrap CDK (First Time Only)
```bash
cd infra
poetry run cdk bootstrap
```

### 2. Validate Configuration
```bash
# Synthesize CloudFormation templates
poetry run cdk synth --all

# Preview changes (optional)
poetry run cdk diff --all
```

### 3. Deploy Infrastructure
```bash
# Deploy all stacks
poetry run cdk deploy --all

# Or deploy specific stack
poetry run cdk deploy ingestion-lab-dev-queues
```

### 4. Verify Deployment
```bash
# Get API endpoint from outputs
aws cloudformation describe-stacks \
  --stack-name ingestion-lab-dev-api \
  --query 'Stacks[0].Outputs[?OutputKey==`ApiUrl`].OutputValue' \
  --output text

# Test health endpoint
curl $API_URL/health

# Send test message
curl -X POST $API_URL/events \
  -H "Content-Type: application/json" \
  -d '{"orderId":"test-123","amount":42.50}'
```

## Post-Deployment

### 1. Confirm SNS Subscription
Check your email for SNS subscription confirmation and click the confirmation link.

### 2. Access Monitoring
- **Dashboard:** AWS Console → CloudWatch → Dashboards → `IngestionLab-{env}`
- **Alarms:** AWS Console → CloudWatch → Alarms
- **Logs:** AWS Console → CloudWatch → Log Groups

### 3. Test Failure Scenarios
```bash
# Enable failure simulation
aws ssm put-parameter \
  --name /ingestion/failure_mode \
  --value poison_payload \
  --type String --overwrite

# Send invalid message to trigger DLQ
curl -X POST $API_URL/events \
  -H "Content-Type: application/json" \
  -d '{"invalid":"data"}'

# Reset to normal operation
aws ssm put-parameter \
  --name /ingestion/failure_mode \
  --value none \
  --type String --overwrite
```

## Troubleshooting

### Common Issues

**CDK Bootstrap Fails**
- Ensure AWS credentials have sufficient permissions
- Check if region supports all required services

**Stack Deployment Fails**
- Check CloudFormation events in AWS Console
- Verify no resource naming conflicts exist
- Ensure account limits aren't exceeded

**Lambda Functions Error**
- Check CloudWatch Logs for specific error messages
- Verify environment variables are set correctly
- Check IAM permissions for Lambda execution role

**No Email Notifications**
- Confirm SNS subscription in email
- Check spam folder
- Verify email address in cdk.json is correct

## Cleanup

To remove all resources:
```bash
cd infra
poetry run cdk destroy --all
```

**Warning:** This will delete all data including DynamoDB tables and CloudWatch logs.