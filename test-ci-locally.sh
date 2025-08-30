#!/bin/bash
set -e

echo "🧪 Testing CI pipeline locally..."

# Activate virtual environment
source .venv/bin/activate

echo "✅ Running tests..."
pytest --cov=infra --cov-report=xml -v

echo "✅ Running linting (critical errors)..."
flake8 infra --count --select=E9,F63,F7,F82 --show-source --statistics --exclude=.venv,cdk.out

echo "✅ Running linting (style warnings)..."
flake8 infra --count --exit-zero --max-complexity=10 --max-line-length=88 --statistics --exclude=.venv,cdk.out

echo "✅ Testing CDK synth..."
cd infra
AWS_DEFAULT_REGION=us-east-1 AWS_ACCOUNT_ID=123456789012 JSII_SILENCE_WARNING_UNTESTED_NODE_VERSION=1 python app.py > /dev/null
cd ..

echo "🎉 All CI checks passed locally!"
echo "Ready to push to GitHub."