Build me an “Event-Driven Ingestion + DLQ Reliability Lab” (Python CDK)
Goal
Create a small, production-style serverless ingestion pipeline: API Gateway → Lambda (ingest) → SQS (standard) → Lambda (worker) with a DLQ + safe redrive, idempotency, observability by default, and break/fix drills that mirror common AWS Support tickets.

Deliverables
CDK app (Python v2) with reusable constructs and tests

Core resources

HTTP API (API Gateway v2): POST /events to accept JSON payloads

Lambda (ingest): validates payload, stamps an idempotencyKey, publishes to SQS

SQS standard queue with DLQ (redrive policy) and SSE-KMS (CMK optional)

Lambda (worker): batch consumes SQS, enforces idempotency with DynamoDB, supports partial batch response

EventBridge bus: emits IngestionSuccess / IngestionFailure events (rules send to SNS or a log Lambda)

DynamoDB table ingestion_state (PK=idempotencyKey): item stores status, checksum, processedAt; TTL for expiry

Redrive tool

Lambda (redrive) + API endpoints: /redrive/start (pull N from DLQ and re-enqueue with jitter), /redrive/preview (sample), /redrive/cancel (no-op but demonstrate control)

Filters by errorType, age, maxMessages, and adds per-message delay (0–900s)

Observability

CloudWatch Dashboard: DLQ depth & age, queue backlog, Lambda errors/throttles/duration, iterator age, EventBridge match counts

Alarms → SNS (email/webhook):

ApproximateAgeOfOldestMessage (main queue, DLQ)

ApproximateNumberOfMessagesVisible (main queue)

Lambda Errors/Throttles (ingest & worker)

Structured JSON logs (ingest + worker): include requestId, idempotencyKey, errorType, latencyMs

Metric filters on errorType and worker processed=true

Break/Fix Lab (toggle with SSM Parameter /ingestion/failure_mode)

poison_payload: worker throws SchemaValidationError → lands in DLQ

slow_downstream: worker sleeps > function timeout to force visibility timeout issues

random_fail_p30: 30% transient failures → demonstrates retries & partial batch response

duplicate_submit: ingest generates same idempotencyKey → worker dedupes

Reset lambda to set failure_mode=none

README with diagram, cost notes, deploy steps, curl examples, runbooks, and interview crib notes

CDK tests (assertions) covering security, wiring, and key config

Repo structure
bash
Copy
Edit
/infra
app.py
cdk.json
requirements.txt
/stacks
api_stack.py
queue_stack.py
functions_stack.py
observability_stack.py
/constructs
kms_key.py
sqs_with_dlq.py
lambda_fn.py
dashboard.py
alarms.py
event_bus.py
/tests
test_queue.py
test_functions.py
/functions
ingest/handler.py
worker/handler.py
redrive/handler.py
common/utils.py
/ops
runbooks/_.md
gamedays/_.md
queries/cloudwatch-insights/\*.txt
Implementation details
SQS + DLQ
Standard queue with DLQ using maxReceiveCount=5 (context-tunable)

Visibility timeout = workerTimeout \* 6 (buffered)

Batch size 10 (context-tunable), maximum batching window 2s

SSE: use AWS-managed SQS key by default; support CMK via context

Lambdas
Ingest:

Validates schema (simple required fields)

Computes idempotencyKey (e.g., SHA256 of canonical payload) unless one is provided

Publishes to SQS with attributes: errorTypeCandidate, submittedAt, idempotencyKey

Worker:

Partial batch response: returns batchItemFailures for only the bad messages

Idempotency: PutItem with ConditionExpression attribute_not_exists(PK); when exists, treat as success (idempotent)

Emits EventBridge events for success/failure with detail (rule → SNS)

Respects /ingestion/failure_mode from SSM to simulate faults

Redrive:

Receives maxMessages, filterErrorType, minAgeSeconds, perMessageDelayJitter

Pulls from DLQ using ReceiveMessage, re-enqueues to main with safe delays (batches ≤ 10)

DynamoDB
PK: idempotencyKey (string)

Attributes: status (SUCCEEDED|FAILED|INFLIGHT), checksum, firstSeenAt, processedAt, attempts

TTL: expiresAt (e.g., 3–7 days)

API (HTTP API v2)
Routes: POST /events (ingest), POST /redrive/start, GET /redrive/preview

Simple JWT or API key auth (context switch)

CORS locked to your site origin

IAM (least privilege)
Ingest: sqs:SendMessage to main queue only

Worker: dynamodb:PutItem/UpdateItem on table, ssm:GetParameter, put EventBridge events to the bus

Redrive: sqs:ReceiveMessage, DeleteMessage on DLQ; SendMessage to main

CloudWatch Logs permissions scoped to each function log group

Observability & alarms
Dashboard widgets:

Queues: Visible msgs, NotVisible msgs, AgeOfOldest (main & DLQ)

Lambdas: Invocations, Errors, Throttles, Duration p95

EventBridge: Matched events count (success/failure)

Alarms (defaults, context-tunable):

DLQ depth > 0 for 5 min

Age of oldest DLQ message > 5 min

Worker Errors > 0 for 5 min

Throttles > 0 for 5 min

Log metric filters on errorType and processed=true

Context (cdk.json)
envName (dev/prod)

maxReceiveCount, batchSize, maxBatchingWindowSeconds

workerTimeoutSeconds, queueVisibilitySeconds

useKmsCmk (bool) and kmsAlias

alarmEmail and/or webhookUrl

authMode (none|apiKey|jwt)

ttlDays for DynamoDB items

Tests (examples)
Main queue has DLQ redrive policy with expected maxReceiveCount

Worker event source has partial batch response enabled and correct batch size

Visibility timeout ≥ workerTimeoutSeconds \* 6

DynamoDB table has TTL enabled

IAM policies limited to specific ARNs

Dashboard and alarms created with expected metrics

Runbooks (create .md)
Poison pill: identify error signature → confirm DLQ growth → run /redrive/preview → fix code/schema → /redrive/start with jitter → confirm drain

Backlog: check VisibleMessages & AgeOfOldest → increase reserved concurrency for worker and/or decrease batch window → verify drop

Timeout vs visibility: when messages reappear, increase visibility; tune function timeout; consider splitting batches

Throttling: raise concurrency limit; add DLQ age alarm; long term: shard queues or use FIFO if ordering matters

Idempotency repair: detect duplicates in DDB; explain why duplicates didn’t break processing

GameDays (scripted)
Schema break (failure_mode=poison_payload) → DLQ grows → run redrive after fix

Slow downstream (failure_mode=slow_downstream) → timeouts → adjust visibility + timeout → verify success

Random fail 30% → observe partial batch behaviour → retries settle

Duplicate submissions → prove dedupe via DDB; show EventBridge success count matches unique payloads

Commands (README)
bash
Copy
Edit

# Deploy

python -m venv .venv && source .venv/bin/activate
pip install -r infra/requirements.txt
cd infra && cdk bootstrap && cdk deploy --all

# Ingest sample event

curl -X POST "$API_URL/events" -H "Content-Type: application/json" -d '{"orderId":"123","amount":42.50}'

# Flip failure modes

aws ssm put-parameter --name /ingestion/failure_mode --value poison_payload --type String --overwrite
aws ssm put-parameter --name /ingestion/failure_mode --value none --type String --overwrite

# Redrive preview & start

curl "$API_URL/redrive/preview?errorType=SchemaValidationError&minAgeSeconds=60&maxMessages=20"
curl -X POST "$API_URL/redrive/start" -H "Content-Type: application/json" -d '{"maxMessages":100,"perMessageDelayJitter":5}'
Acceptance criteria
cdk deploy works in a fresh account; API accepts events and items appear in DDB as SUCCEEDED

DLQ alarms fire during poison_payload; dashboard shows backlog and age growth

Redrive endpoint successfully moves messages back with jitter and drains DLQ

Worker logs show partial batch response behaviour; duplicates don’t create duplicate records

All unit tests (assertions) pass in CI

Interview crib notes (add to README)
At-least-once delivery → duplicates can happen; solve with idempotency and partial batch response.

Timeout vs visibility: visibility must exceed function timeout (plus buffer) or messages re-surface.

Backpressure levers: batch size, batching window, reserved concurrency, DLQ policy, redrive pacing.

DLQ redrive safety: filter, throttle, add jitter; never blind-replay everything at once.

FIFO vs Standard: Standard for throughput; FIFO when strict ordering + exactly-once with dedupe (tradeoffs).

Build exactly as above. Default to the secure, supportable choice and document any deviations in the README.
