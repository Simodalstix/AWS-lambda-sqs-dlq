# GameDay: Schema Evolution & Breaking Changes

## 🎯 Scenario Overview

**Objective**: Test the pipeline's resilience to schema changes and practice DLQ recovery procedures  
**Duration**: 2-3 hours  
**Participants**: DevOps, Backend Engineers, SRE  
**Difficulty**: Intermediate

## 📋 Prerequisites

- Ingestion pipeline deployed and healthy
- Access to AWS Console and CLI
- Monitoring dashboard accessible
- Team communication channel ready

## 🎮 Scenario Timeline

### Phase 1: Baseline Establishment (15 minutes)

#### 1.1 Verify System Health

```bash
# Check all components are healthy
curl $API_URL/health

# Verify DLQ is empty
aws sqs get-queue-attributes \
  --queue-url $DLQ_URL \
  --attribute-names ApproximateNumberOfMessages

# Send baseline traffic
for i in {1..20}; do
  curl -X POST $API_URL/events \
    -H "Content-Type: application/json" \
    -d "{\"orderId\":\"baseline-$i\",\"amount\":$(($RANDOM % 100 + 1))}" &
done
wait
```

#### 1.2 Document Baseline Metrics

- [ ] Main queue depth: \_\_\_
- [ ] DLQ depth: \_\_\_
- [ ] Lambda error rate: \_\_\_
- [ ] API success rate: \_\_\_

### Phase 2: Schema Change Introduction (30 minutes)

#### 2.1 Simulate Breaking Schema Change

```bash
# Enable poison payload mode to simulate schema validation failures
aws ssm put-parameter \
  --name /ingestion/failure_mode \
  --value poison_payload \
  --type String --overwrite

echo "✅ Poison payload mode enabled - new requests will fail validation"
```

#### 2.2 Generate Traffic with "New Schema"

```bash
# Simulate clients sending new schema that fails validation
for i in {1..50}; do
  curl -X POST $API_URL/events \
    -H "Content-Type: application/json" \
    -d "{\"orderId\":\"new-schema-$i\",\"amount\":$(($RANDOM % 100 + 1)),\"newField\":\"breaking-change\"}" &

  # Mix with some valid requests
  if [ $((i % 5)) -eq 0 ]; then
    curl -X POST $API_URL/events \
      -H "Content-Type: application/json" \
      -d "{\"orderId\":\"valid-$i\",\"amount\":$(($RANDOM % 100 + 1))}" &
  fi
done
wait
```

#### 2.3 Observe System Behavior

**Expected Outcomes**:

- DLQ depth should increase
- API returns 400 errors for invalid payloads
- Valid payloads continue processing normally
- Alarms should trigger

**Monitoring Tasks**:

```bash
# Watch DLQ growth
watch -n 5 'aws sqs get-queue-attributes --queue-url $DLQ_URL --attribute-names ApproximateNumberOfMessages'

# Check alarm status
aws cloudwatch describe-alarms \
  --alarm-names "IngestionLab-DLQ-Depth" \
  --query 'MetricAlarms[0].StateValue'
```

### Phase 3: Incident Response (45 minutes)

#### 3.1 Alarm Investigation (15 minutes)

**Team Exercise**: Follow the [DLQ Depth Alarm Runbook](../runbooks/dlq-depth-alarm.md)

**Key Actions**:

1. Assess impact and scope
2. Check recent changes (SSM parameter)
3. Analyze error patterns in DLQ
4. Identify root cause (schema validation failures)

```bash
# Preview DLQ messages
curl "$API_URL/redrive/preview?maxMessages=10&minAgeSeconds=60"

# Check error patterns in logs
aws logs start-query \
  --log-group-name "/aws/lambda/ingestion-ingest-dev" \
  --start-time $(date -d '1 hour ago' +%s) \
  --end-time $(date +%s) \
  --query-string 'fields @timestamp, @message, error | filter @message like /Validation failed/ | stats count() by error'
```

#### 3.2 Implement Fix (15 minutes)

**Scenario**: Update validation logic to handle new field

```bash
# Simulate deploying backward-compatible validation
# In real scenario, this would be a code deployment
aws ssm put-parameter \
  --name /ingestion/failure_mode \
  --value none \
  --type String --overwrite

echo "✅ Schema validation updated to handle new field"
```

#### 3.3 Verify Fix (15 minutes)

```bash
# Test new schema now works
curl -X POST $API_URL/events \
  -H "Content-Type: application/json" \
  -d '{"orderId":"test-new-schema","amount":42.50,"newField":"now-supported"}'

# Verify processing
aws logs tail /aws/lambda/ingestion-worker-dev --follow
```

### Phase 4: Message Recovery (30 minutes)

#### 4.1 Plan Recovery Strategy

**Discussion Points**:

- How many messages are in DLQ?
- What's the business impact of delayed processing?
- Should we redrive all at once or in batches?
- What safety measures should we implement?

#### 4.2 Execute Safe Redrive

```bash
# Step 1: Small test batch
curl -X POST $API_URL/redrive/start \
  -H "Content-Type: application/json" \
  -d '{
    "maxMessages": 5,
    "minAgeSeconds": 300,
    "perMessageDelayJitter": 1
  }'

# Monitor processing
echo "Monitoring small batch redrive..."
sleep 30

# Step 2: Larger batch if successful
curl -X POST $API_URL/redrive/start \
  -H "Content-Type: application/json" \
  -d '{
    "maxMessages": 50,
    "minAgeSeconds": 300,
    "perMessageDelayJitter": 3
  }'
```

#### 4.3 Monitor Recovery

```bash
# Watch queue depths
watch -n 10 'echo "Main Queue:" && aws sqs get-queue-attributes --queue-url $QUEUE_URL --attribute-names ApproximateNumberOfMessages && echo "DLQ:" && aws sqs get-queue-attributes --queue-url $DLQ_URL --attribute-names ApproximateNumberOfMessages'

# Check processing success rate
aws cloudwatch get-metric-statistics \
  --namespace AWS/Lambda \
  --metric-name Invocations \
  --dimensions Name=FunctionName,Value=ingestion-worker-dev \
  --start-time $(date -d '10 minutes ago' --iso-8601) \
  --end-time $(date --iso-8601) \
  --period 60 \
  --statistics Sum
```

### Phase 5: Validation & Cleanup (20 minutes)

#### 5.1 Verify System Recovery

```bash
# Confirm DLQ is empty
aws sqs get-queue-attributes \
  --queue-url $DLQ_URL \
  --attribute-names ApproximateNumberOfMessages

# Test end-to-end flow
curl -X POST $API_URL/events \
  -H "Content-Type: application/json" \
  -d '{"orderId":"final-test","amount":99.99,"newField":"supported"}'

# Verify processing and EventBridge events
```

#### 5.2 Reset Environment

```bash
# Ensure failure mode is disabled
aws ssm put-parameter \
  --name /ingestion/failure_mode \
  --value none \
  --type String --overwrite

# Verify alarms have cleared
aws cloudwatch describe-alarms \
  --alarm-names "IngestionLab-DLQ-Depth" \
  --query 'MetricAlarms[0].StateValue'
```

## 📊 Success Criteria

### ✅ Technical Objectives

- [ ] DLQ alarm triggered when messages failed
- [ ] Team followed runbook procedures correctly
- [ ] Root cause identified within 15 minutes
- [ ] Fix implemented and verified
- [ ] All messages successfully redriven
- [ ] No data loss occurred
- [ ] System returned to healthy state

### ✅ Process Objectives

- [ ] Clear communication maintained throughout
- [ ] Roles and responsibilities understood
- [ ] Escalation procedures known
- [ ] Documentation proved useful
- [ ] Monitoring provided adequate visibility

## 🎓 Learning Outcomes

### Key Takeaways

1. **Schema Evolution Strategy**: How to handle breaking changes gracefully
2. **Monitoring Effectiveness**: Which metrics and alarms were most useful
3. **Recovery Procedures**: Safe practices for DLQ redrive operations
4. **Team Coordination**: Communication patterns during incidents

### Discussion Questions

- What would happen if we had 10,000 messages in the DLQ?
- How could we prevent this scenario in production?
- What additional monitoring would be helpful?
- How would we handle this during peak traffic hours?

## 🔄 Variations & Advanced Scenarios

### Variation A: Partial Schema Support

- Deploy fix that only handles 50% of new schema cases
- Practice handling mixed success/failure scenarios

### Variation B: Downstream Dependency Failure

- Combine schema issues with simulated downstream outage
- Test cascading failure handling

### Variation C: High Volume Impact

- Generate 1000+ failed messages
- Practice large-scale recovery operations

## 📝 Post-GameDay Actions

### Immediate (Day 0)

- [ ] Document lessons learned
- [ ] Update runbooks based on findings
- [ ] Fix any monitoring gaps identified
- [ ] Share results with broader team

### Short-term (Week 1)

- [ ] Implement process improvements
- [ ] Update alerting thresholds if needed
- [ ] Enhance automation where possible
- [ ] Schedule follow-up scenarios

### Long-term (Month 1)

- [ ] Review schema evolution strategy
- [ ] Consider implementing schema registry
- [ ] Evaluate circuit breaker patterns
- [ ] Plan advanced GameDay scenarios

## 📞 Emergency Contacts

- **GameDay Facilitator**: [Name/Contact]
- **On-call Engineer**: [PagerDuty/Slack]
- **AWS Support**: [Case escalation process]

## 📚 Reference Materials

- [DLQ Depth Alarm Runbook](../runbooks/dlq-depth-alarm.md)
- [API Documentation](../api-reference.md)
- [CloudWatch Dashboard](https://console.aws.amazon.com/cloudwatch/home#dashboards:name=IngestionLab-dev)
- [Architecture Diagram](../../README.md#architecture)

---

**Remember**: This is a learning exercise. Take time to understand each step and discuss alternatives with your team.
