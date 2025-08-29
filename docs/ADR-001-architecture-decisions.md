# ADR-001: Core Architecture Decisions

**Status:** Accepted  
**Date:** 2024-01-15  
**Deciders:** Development Team  

## Context

We need to build a reliable, scalable serverless ingestion pipeline that can handle high throughput while maintaining message durability and operational visibility.

## Decision

### 1. SQS Standard Queue over FIFO Queue
**Chosen:** SQS Standard Queue  
**Rationale:** Higher throughput (unlimited TPS vs 3000 TPS), better cost efficiency, and at-least-once delivery is acceptable for our use case with idempotency handling.

### 2. HTTP API Gateway v2 over REST API
**Chosen:** HTTP API Gateway v2  
**Rationale:** 70% cost reduction, better performance, simpler configuration, and sufficient features for our API needs.

### 3. DynamoDB for Idempotency over Redis/ElastiCache
**Chosen:** DynamoDB  
**Rationale:** Serverless (no infrastructure management), automatic scaling, TTL support, and consistent with AWS serverless ecosystem.

### 4. EventBridge over Direct SNS
**Chosen:** EventBridge with SNS integration  
**Rationale:** Better event routing capabilities, schema registry support, and easier integration with future event-driven services.

### 5. CDK over CloudFormation/Terraform
**Chosen:** AWS CDK (Python)  
**Rationale:** Type safety, better abstraction, reusable constructs, and native AWS service support with faster feature adoption.

## Consequences

### Positive
- High throughput and cost-effective solution
- Strong operational visibility and monitoring
- Serverless architecture reduces operational overhead
- Type-safe infrastructure as code

### Negative
- SQS Standard Queue requires idempotency handling
- Learning curve for CDK vs traditional IaC tools
- Vendor lock-in to AWS ecosystem

## Alternatives Considered

1. **Kinesis Data Streams:** Rejected due to complexity and cost for simple message processing
2. **Step Functions:** Rejected as orchestration overhead not needed for linear processing
3. **RDS for idempotency:** Rejected due to operational overhead and scaling concerns

## Monitoring

We will monitor:
- Message processing latency and throughput
- DLQ depth and message age
- Cost per processed message
- Infrastructure deployment success rate