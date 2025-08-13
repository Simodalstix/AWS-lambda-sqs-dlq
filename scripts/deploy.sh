#!/bin/bash

# Event-Driven Ingestion + DLQ Reliability Lab - Deployment Script
# This script deploys the complete ingestion pipeline infrastructure

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
ENV_NAME=${ENV_NAME:-dev}
REGION=${AWS_DEFAULT_REGION:-us-east-1}
ALARM_EMAIL=${ALARM_EMAIL:-devops@example.com}

echo -e "${BLUE}🚀 Event-Driven Ingestion + DLQ Reliability Lab Deployment${NC}"
echo -e "${BLUE}Environment: ${ENV_NAME}${NC}"
echo -e "${BLUE}Region: ${REGION}${NC}"
echo ""

# Function to print status
print_status() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

# Check prerequisites
echo -e "${BLUE}📋 Checking Prerequisites...${NC}"

# Check AWS CLI
if ! command -v aws &> /dev/null; then
    print_error "AWS CLI not found. Please install AWS CLI."
    exit 1
fi

# Check CDK CLI
if ! command -v cdk &> /dev/null; then
    print_error "CDK CLI not found. Please install AWS CDK CLI: npm install -g aws-cdk"
    exit 1
fi

# Check Python
if ! command -v python3 &> /dev/null; then
    print_error "Python 3 not found. Please install Python 3.9+."
    exit 1
fi

# Check AWS credentials
if ! aws sts get-caller-identity &> /dev/null; then
    print_error "AWS credentials not configured. Please run 'aws configure'."
    exit 1
fi

print_status "Prerequisites check passed"

# Get AWS account and region info
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
CURRENT_REGION=$(aws configure get region)
REGION=${CURRENT_REGION:-$REGION}

echo -e "${BLUE}Account ID: ${ACCOUNT_ID}${NC}"
echo -e "${BLUE}Region: ${REGION}${NC}"
echo ""

# Setup Python environment
echo -e "${BLUE}🐍 Setting up Python Environment...${NC}"

if [ ! -d ".venv" ]; then
    print_status "Creating Python virtual environment"
    python3 -m venv .venv
fi

print_status "Activating virtual environment"
source .venv/bin/activate

print_status "Installing Python dependencies"
pip install -r infra/requirements.txt > /dev/null 2>&1

# CDK Bootstrap (if needed)
echo -e "${BLUE}🏗️  CDK Bootstrap Check...${NC}"

# Check if CDK is bootstrapped
if ! aws cloudformation describe-stacks --stack-name CDKToolkit --region $REGION &> /dev/null; then
    print_warning "CDK not bootstrapped in this region. Bootstrapping now..."
    cd infra
    cdk bootstrap aws://$ACCOUNT_ID/$REGION
    cd ..
    print_status "CDK bootstrap completed"
else
    print_status "CDK already bootstrapped"
fi

# Set CDK context
echo -e "${BLUE}⚙️  Configuring CDK Context...${NC}"

cd infra

# Update cdk.json with environment-specific values
if [ "$ALARM_EMAIL" != "devops@example.com" ]; then
    print_status "Setting alarm email to: $ALARM_EMAIL"
    # Note: In a real deployment, you'd use jq or similar to update cdk.json
    # For this demo, we'll use CDK context override
fi

# Deploy stacks
echo -e "${BLUE}🚀 Deploying CDK Stacks...${NC}"

print_status "Starting CDK deployment (this may take 10-15 minutes)"

# Deploy with context overrides
cdk deploy --all \
    --context envName=$ENV_NAME \
    --context alarmEmail=$ALARM_EMAIL \
    --require-approval never \
    --outputs-file ../outputs.json

if [ $? -eq 0 ]; then
    print_status "CDK deployment completed successfully"
else
    print_error "CDK deployment failed"
    exit 1
fi

cd ..

# Extract outputs
echo -e "${BLUE}📄 Extracting Deployment Outputs...${NC}"

if [ -f "outputs.json" ]; then
    API_URL=$(cat outputs.json | python3 -c "
import json, sys
data = json.load(sys.stdin)
for stack_name, outputs in data.items():
    if 'ApiUrl' in outputs:
        print(outputs['ApiUrl'])
        break
")
    
    if [ -n "$API_URL" ]; then
        print_status "API Gateway URL: $API_URL"
        echo "$API_URL" > api_url.txt
    fi
fi

# Create environment file
echo -e "${BLUE}📝 Creating Environment Configuration...${NC}"

cat > .env << EOF
# Event-Driven Ingestion + DLQ Reliability Lab Environment
ENV_NAME=$ENV_NAME
AWS_REGION=$REGION
AWS_ACCOUNT_ID=$ACCOUNT_ID
API_URL=$API_URL
ALARM_EMAIL=$ALARM_EMAIL

# Queue URLs (retrieve from SSM)
QUEUE_URL=\$(aws ssm get-parameter --name /ingestion/queue_url --query Parameter.Value --output text)
DLQ_URL=\$(aws ssm get-parameter --name /ingestion/dlq_url --query Parameter.Value --output text)

# EventBridge Bus
EVENT_BUS_NAME=\$(aws ssm get-parameter --name /ingestion/event_bus_name --query Parameter.Value --output text)

# DynamoDB Table
IDEMPOTENCY_TABLE=\$(aws ssm get-parameter --name /ingestion/idempotency_table --query Parameter.Value --output text)
EOF

print_status "Environment configuration saved to .env"

# Test deployment
echo -e "${BLUE}🧪 Testing Deployment...${NC}"

if [ -n "$API_URL" ]; then
    print_status "Testing health endpoint"
    
    HEALTH_RESPONSE=$(curl -s -o /dev/null -w "%{http_code}" "$API_URL/health")
    
    if [ "$HEALTH_RESPONSE" = "200" ]; then
        print_status "Health check passed"
    else
        print_warning "Health check returned status: $HEALTH_RESPONSE"
    fi
    
    print_status "Testing event ingestion"
    
    INGEST_RESPONSE=$(curl -s -o /dev/null -w "%{http_code}" \
        -X POST "$API_URL/events" \
        -H "Content-Type: application/json" \
        -d '{"orderId":"deploy-test-'$(date +%s)'","amount":42.50}')
    
    if [ "$INGEST_RESPONSE" = "202" ]; then
        print_status "Event ingestion test passed"
    else
        print_warning "Event ingestion returned status: $INGEST_RESPONSE"
    fi
else
    print_warning "API URL not found in outputs, skipping tests"
fi

# Display summary
echo ""
echo -e "${GREEN}🎉 Deployment Summary${NC}"
echo -e "${GREEN}===================${NC}"
echo -e "Environment: ${ENV_NAME}"
echo -e "Region: ${REGION}"
echo -e "Account: ${ACCOUNT_ID}"
if [ -n "$API_URL" ]; then
    echo -e "API URL: ${API_URL}"
fi
echo -e "Dashboard: https://console.aws.amazon.com/cloudwatch/home?region=${REGION}#dashboards:name=IngestionLab-${ENV_NAME}"
echo ""

# Next steps
echo -e "${BLUE}📋 Next Steps:${NC}"
echo "1. Source environment variables: source .env"
echo "2. Test the pipeline: ./scripts/test-pipeline.sh"
echo "3. View monitoring dashboard in AWS Console"
echo "4. Try GameDay scenarios: ops/gamedays/"
echo "5. Review operational runbooks: ops/runbooks/"
echo ""

# Cleanup function
cleanup() {
    if [ -f ".venv/bin/activate" ]; then
        deactivate 2>/dev/null || true
    fi
}

trap cleanup EXIT

print_status "Deployment completed successfully! 🚀"