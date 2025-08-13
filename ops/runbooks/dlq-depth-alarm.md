# Runbook: DLQ Depth Alarm

## 🚨 Alert Description

**Alarm**: `IngestionLab-DLQ-Depth`  
**Severity**: Critical  
**Condition**: Dead Letter Queue has 1 or more messages

## 📋 Immediate Actions (5 minutes)

### 1. Assess Impact

```bash
# Check current DLQ depth
aws sqs get-queue-attributes \
  --queue-url $DLQ_URL \
  --attribute-names ApproximateNumberOfMessages

# Check main queue backlog
aws sqs get-queue-attributes \
  --queue-url $QUEUE_URL \
  --attribute-names ApproximateNumberOfMessages,ApproximateAgeOfOldestMessage
```

### 2. Quick Triage

- **Low volume (< 10 messages)**: Likely isolated failures, proceed with investigation
- **High volume (> 100 messages)**: Potential systemic issue, escalate immediately
- **Growing rapidly**: Stop ingestion if possible, investigate root cause

## 🔍 Investigation (15 minutes)

### 1. Check Recent Changes

```bash
# Review recent deployments
aws logs describe-log-groups --log-group-name-prefix "/aws/lambda/ingestion"

# Check SSM parameter changes
aws ssm get-parameter-history --name /ingestion/failure_mode
```

### 2. Analyze Error Patterns

```bash
# Preview DLQ messages
curl "$API_URL/redrive/preview?maxMessages=20&minAgeSeconds=60"

# Check CloudWatch Logs for errors
aws logs start-query \
  --log-group-name "/aws/lambda/ingestion-worker-dev" \
  --start-time $(date -d '1 hour ago' +%s) \
  --end-time $(date +%s) \
  --query-string 'fields @timestamp, @message, errorType, idempotencyKey | filter @message like /ERROR/ | sort @timestamp desc | limit 50'
```

### 3. Review Dashboard

- Navigate to CloudWatch Dashboard: `IngestionLab-{env}`
- Check Lambda error rates and duration
- Verify API Gateway error rates
- Review custom metrics for validation errors

## 🛠️ Common Root Causes & Solutions

### Schema Validation Errors

**Symptoms**: `errorType: SchemaValidationError` in DLQ messages  
**Cause**: Invalid payload structure or missing required fields

**Solution**:

```bash
# Check validation error patterns
aws logs start-query \
  --log-group-name "/aws/lambda/ingestion-ingest-dev" \
  --start-time $(date -d '2 hours ago' +%s) \
  --end-time $(date +%s) \
  --query-string 'fields @timestamp, @message, error | filter @message like /Validation failed/ | stats count() by error'

# If schema change needed, deploy fix first, then redrive
```

### Downstream Service Outage

**Symptoms**: `errorType: TimeoutError` or `ProcessingError`  
**Cause**: External service unavailable or slow

**Solution**:

```bash
# Check if failure mode is set
aws ssm get-parameter --name /ingestion/failure_mode

# If real outage, implement circuit breaker or wait for recovery
# Monitor service health before redriving
```

### DynamoDB Throttling

**Symptoms**: `ProvisionedThroughputExceededException` in logs  
**Cause**: High write volume exceeding table capacity

**Solution**:

```bash
# Check DynamoDB metrics
aws cloudwatch get-metric-statistics \
  --namespace AWS/DynamoDB \
  --metric-name ThrottledRequests \
  --dimensions Name=TableName,Value=ingestion-state-dev \
  --start-time $(date -d '1 hour ago' --iso-8601) \
  --end-time $(date --iso-8601) \
  --period 300 \
  --statistics Sum

# Consider increasing table capacity or implementing backoff
```

### Lambda Function Errors

**Symptoms**: Function errors in CloudWatch metrics  
**Cause**: Code bugs, memory issues, or timeout

**Solution**:

```bash
# Check function metrics
aws cloudwatch get-metric-statistics \
  --namespace AWS/Lambda \
  --metric-name Errors \
  --dimensions Name=FunctionName,Value=ingestion-worker-dev \
  --start-time $(date -d '1 hour ago' --iso-8601) \
  --end-time $(date --iso-8601) \
  --period 300 \
  --statistics Sum

# Review function logs for specific error details
```

## 🔄 Message Recovery

### 1. Safe Redrive Process

```bash
# Step 1: Preview messages (understand scope)
curl "$API_URL/redrive/preview?maxMessages=50&minAgeSeconds=300"

# Step 2: Start with small batch
curl -X POST $API_URL/redrive/start \
  -H "Content-Type: application/json" \
  -d '{
    "maxMessages": 10,
    "minAgeSeconds": 300,
    "perMessageDelayJitter": 2
  }'

# Step 3: Monitor processing
# Check main queue depth and worker metrics

# Step 4: Scale up if successful
curl -X POST $API_URL/redrive/start \
  -H "Content-Type: application/json" \
  -d '{
    "maxMessages": 100,
    "minAgeSeconds": 300,
    "perMessageDelayJitter": 5
  }'
```

### 2. Redrive Safety Checklist

- [ ] Root cause identified and fixed
- [ ] Downstream services healthy
- [ ] Worker function processing normally
- [ ] Started with small batch (< 20 messages)
- [ ] Added appropriate jitter (2-10 minutes)
- [ ] Monitoring queue depths during redrive

## 📊 Monitoring During Recovery

### Key Metrics to Watch

```bash
# Main queue depth (should decrease)
aws cloudwatch get-metric-statistics \
  --namespace AWS/SQS \
  --metric-name ApproximateNumberOfMessages \
  --dimensions Name=QueueName,Value=ingestion-queue-dev \
  --start-time $(date -d '30 minutes ago' --iso-8601) \
  --end-time $(date --iso-8601) \
  --period 60 \
  --statistics Average

# Worker function success rate
aws cloudwatch get-metric-statistics \
  --namespace AWS/Lambda \
  --metric-name Invocations \
  --dimensions Name=FunctionName,Value=ingestion-worker-dev \
  --start-time $(date -d '30 minutes ago' --iso-8601) \
  --end-time $(date --iso-8601) \
  --period 300 \
  --statistics Sum
```

## ✅ Resolution Verification

### 1. Confirm DLQ is Empty

```bash
aws sqs get-queue-attributes \
  --queue-url $DLQ_URL \
  --attribute-names ApproximateNumberOfMessages
```

### 2. Verify Normal Processing

```bash
# Send test message
curl -X POST $API_URL/events \
  -H "Content-Type: application/json" \
  -d '{"orderId":"test-recovery-'$(date +%s)'","amount":1.00}'

# Check processing in logs
aws logs tail /aws/lambda/ingestion-worker-dev --follow
```

### 3. Update Monitoring

- Confirm alarm has cleared
- Document root cause in incident log
- Update runbook if new patterns discovered

## 🔄 Post-Incident Actions

### 1. Root Cause Analysis

- Document timeline of events
- Identify contributing factors
- Review monitoring gaps
- Plan preventive measures

### 2. Process Improvements

- Update validation rules if needed
- Adjust alarm thresholds if appropriate
- Enhance error handling in code
- Improve monitoring coverage

### 3. Team Communication

- Share findings with team
- Update documentation
- Schedule post-mortem if significant impact

## 📞 Escalation

**Escalate if**:

- DLQ depth > 1000 messages
- Root cause unclear after 30 minutes
- Redrive operations failing
- Customer impact reported

**Escalation Contacts**:

- On-call Engineer: [Slack/PagerDuty]
- Team Lead: [Contact info]
- Platform Team: [Contact info]

## 📚 Related Documentation

- [API Documentation](../api-reference.md)
- [Architecture Overview](../../README.md#architecture)
- [Monitoring Dashboard](https://console.aws.amazon.com/cloudwatch/home#dashboards:name=IngestionLab-dev)
- [GameDay Scenarios](../gamedays/)
