---
name: stack-backend
description: Backend/API profile (Node, Python, Go, Java/Kotlin, .NET, Ruby; REST, GraphQL, gRPC, workers) — spec, plan, implementation and verification specifics for services. Load when CLAUDE.md Stack profile includes backend.
user-invocable: false
---

## Spec additions
- Who calls it (roles, services) and authorisation per operation.
- Limits: payload size, rate limits, pagination, timeouts; idempotency for retries.
- Data retention, PII classification, audit needs.
- SLO if relevant (e.g. p95 < 300 ms at N rps).

## Plan additions
- Contract first: OpenAPI / GraphQL schema / proto diff; versioning and backward compatibility.
- Data: migration + rollback + backfill; zero-downtime pattern (expand → migrate → contract).
- Async work: queue, retries with backoff, dead-letter, exactly-once vs at-least-once.
- Observability: logs (no PII), metrics, traces, alerts for the new path.
- Config: new env vars with safe defaults; per-environment values are a human step.

## Implementation
- Validate input at the boundary; return the project's standard error shape.
- Authz check on every new entry point, tested with a forbidden case.
- Parameterised queries only; no string-built SQL.
- Time in UTC; money in integer minor units or decimal types.

## Verification
- Unit tests for domain logic; integration tests against real dependencies in containers (Testcontainers / docker compose).
- Contract tests or schema validation for the API.
- Migration tested up and down on a seeded database, including conflicting data.
- Smoke the running service locally with real HTTP calls for each AC.
