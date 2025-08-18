# Interview Crib Notes: Event-Driven Ingestion + DLQ Reliability Lab

## 🎯 Key Concepts & Best Practices

### At-least-once Delivery

**Problem**: SQS guarantees message delivery but may deliver duplicates
**Solution**: Idempotency patterns with DynamoDB
**Implementation**:

- Generate deterministic idempotency keys (SHA256 of payload)
- Use conditional writes (`attribute_not_exists`)
- Set TTL for cleanup (3-7 days)

### Visibility Timeout vs Function Timeout

**Problem**: Messages reappear if visibility timeout < function processing time
**Solution**: Visibility timeout = workerTimeout \* 6 (buffered)
**Best Practice**: Monitor `ApproximateAgeOfOldestMessage` metric

### Partial Batch Response

**Problem**: Entire batch retries when only some messages fail
**Solution**: Return `batchItemFailures` with only failed message IDs
**Benefit**: Reduces duplicate processing and improves throughput

### Backpressure Management

**Levers**:

- Batch size (1-10 messages)
- Batching window (0-300 seconds)
- Reserved concurrency (limit parallel executions)
- DLQ policy (maxReceiveCount for retry limits)
- Redrive pacing (jitter, throttling)

### DLQ Redrive Safety

**Always**:

- Filter by error type and age
- Add per-message delay (jitter)
- Limit batch sizes (< 100 messages)
- Never blind-replay everything

**Never**:

- Redrive without root cause analysis
- Ignore message age (recent failures may still be valid)
- Replay without safety controls

## 🏗️ Architecture Decisions

### Standard vs FIFO Queues

**Standard**: High throughput, at-least-once delivery
**FIFO**: Strict ordering, exactly-once processing (lower throughput)

### Push vs Pull Processing

**SQS → Lambda (Pull)**: Better for cost efficiency and backpressure
**API → Lambda (Push)**: Immediate feedback for synchronous requests

### Synchronous vs Asynchronous Processing

**API Gateway → Lambda**: For immediate validation and response
**SQS → Lambda**: For reliable background processing

## 🛡️ Security Patterns

### Least Privilege IAM

- Function-specific policies with minimal required permissions
- Resource-based restrictions (specific queue/table ARNs)
- No wildcard permissions in production

### Encryption

- KMS-managed encryption for queues and tables (default)
- Customer-managed keys (CMK) for enhanced control
- Environment-specific key aliases

## 🔍 Observability Strategy

### Structured Logging

- JSON format with correlation IDs
- Standard fields: timestamp, level, logger, message
- Context enrichment with requestId, idempotencyKey

### Custom Metrics

- Business metrics from log filters
- Error type distribution
- Processing success rates
- Idempotency hit ratios

### Distributed Tracing

- X-Ray for request flow tracking
- AWS X-Ray SDK integration
- End-to-end request correlation

## 🚨 Reliability Patterns

### Circuit Breaker

- SSM parameter for failure mode control
- Simulated errors for testing (poison payload, timeout)
- Graceful degradation strategies

### Retry Strategies

- SQS built-in retries (maxReceiveCount)
- Exponential backoff with jitter
- Dead letter queue for persistent failures

### Idempotency Implementation

```python
# DynamoDB conditional write pattern
table.put_item(
    Item={
        'idempotencyKey': idempotency_key,
        'status': 'INFLIGHT',
        # ... other attributes
    },
    ConditionExpression=Attr('idempotencyKey').not_exists()
)
```

## 💰 Cost Optimization

### Lambda Pricing

- Duration-based billing (1ms increments)
- Memory allocation affects cost and performance
- ARM64 architecture for better price/performance

### SQS Pricing

- Per-request pricing (sent, received, deleted)
- Standard queues for high throughput
- Batch operations to reduce request count

### DynamoDB Pricing

- Pay-per-request (read/write capacity units)
- TTL for automatic cleanup
- Consider provisioned capacity for predictable workloads

## 🧪 Testing Strategies

### Unit Testing

- CDK assertions for infrastructure validation
- Mock AWS services with moto/boto3
- Test security configurations and wiring

### Integration Testing

- End-to-end flow verification
- Failure mode simulation
- Load testing with realistic payloads

### GameDay Exercises

- Planned failure injection
- Team coordination practice
- Runbook validation and improvement

## 📈 Monitoring & Alerting

### Critical Alarms

- DLQ depth > 0 for 5 minutes
- Age of oldest DLQ message > 5 minutes
- Worker function errors > 0 for 5 minutes

### Warning Alarms

- Main queue backlog growth
- High latency patterns
- Throttling events

### Dashboard Widgets

- Queue depths and ages
- Lambda invocation rates and errors
- API Gateway request/response patterns
- Custom business metrics

## 🔄 Operational Excellence

### Deployment Strategy

- Infrastructure as Code (CDK v2)
- Environment-specific contexts
- Automated testing in CI/CD pipeline

### Incident Response

- Pre-defined runbooks for common scenarios
- CloudWatch Insights queries for troubleshooting
- Safe redrive procedures with validation

### Maintenance Windows

- Scheduled updates with rollback plans
- Canary deployments for function updates
- Blue/green deployments for infrastructure changes

## 📚 Common Interview Questions

### "How do you handle duplicate messages?"

Implement idempotency with DynamoDB conditional writes and deterministic keys.

### "What's the difference between visibility timeout and function timeout?"

Visibility timeout must exceed function timeout plus buffer to prevent message reprocessing.

### "How do you safely redrive messages from DLQ?"

Filter by error type and age, add jitter, limit batch sizes, and verify root cause is fixed.

### "What monitoring is critical for this system?"

DLQ depth, queue age, Lambda errors/throttles, API Gateway errors, and custom business metrics.

### "How do you optimize costs?"

Right-size Lambda memory, batch SQS operations, use ARM64 architecture, and implement TTL for DynamoDB.

## 🎮 Advanced Topics

### Chaos Engineering

- Planned failure injection scenarios
- Team response time measurement
- System resilience validation

### Performance Tuning

- Memory allocation optimization
- Batch size and window tuning
- Concurrency limit adjustments

### Security Auditing

- IAM policy least privilege reviews
- Encryption at rest and in transit
- Access logging and monitoring

---

**Remember**: These patterns are battle-tested in production environments and represent AWS best practices for serverless reliability and operational excellence.
