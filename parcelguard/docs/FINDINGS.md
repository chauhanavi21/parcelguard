# ParcelGuard: measured findings

Regenerate with `python verify.py` or `python evidence.py`. The [order evidence](../artifacts/order-evidence.json) uses a fresh temporary database; the [retry study](../artifacts/retry-study.json) contains all timelines and metrics.

## Order recovery

One order reserves two trail packs. A repeated key returns the same saved order; changed quantity conflicts. An injected failure before an unrelated outbox write leaves the entire pre-failure snapshot unchanged. With the ACK deliberately lost, one consumer effect is committed and one event awaits retry. After advancing time and retrying, the duplicate is suppressed: one order, one effect, two claims, and trail-pack stock 118 of the initial 120. All seven evidence assertions pass.

This establishes the tested local transactional/idempotency behavior. It does not establish exactly-once external delivery, safe real payment retries, or a distributed recovery guarantee. The consumer and outbox share one database file but use separate transactions.

## Retry study: synchronized contention

120 clients, capacity 15 attempts/100 ms, at most six attempts/client.

| Seed | Immediate: completed / attempts / success p95 | Exponential: completed / attempts / success p95 | Full jitter: completed / attempts / success p95 |
|---|---|---|---|
| 7 | 14 / 650 / 25 ms | 85 / 507 / 6,225 ms | 120 / 381 / 1,561 ms |
| 42 | 14 / 650 / 25 ms | 87 / 506 / 6,225 ms | 120 / 372 / 1,118 ms |
| 2026 | 13 / 655 / 25 ms | 86 / 510 / 6,225 ms | 120 / 377 / 1,339 ms |

Jitter spreads work across capacity slots and completes all clients in these constructed runs with fewer total attempts. Immediate retries largely remain in the overloaded slot and exhaust their budget. The low latency for immediate retries describes the small successful subset, so it is misleading without the failure count.

## Retry study: spare capacity

40 clients, capacity 100 attempts/100 ms. All three strategies complete every client for seeds 7, 42, and 2026. Each uses 41, 43, and 43 attempts respectively. With seed 42, immediate retry has a successful-client p95 of 26 ms, exponential backoff 225 ms, and full jitter 73 ms. Here waiting adds delay without reducing the total attempt count. Seed 2026 has the same immediate/exponential p95 and jitter p95 of 75 ms; seed 7's p95 is 25 ms for all strategies.

The model therefore supports a workload-specific conclusion about contention and retry scheduling. It does not show that jitter always wins. Synchronized arrivals, fixed bucket capacity, stable ID tie-breaking, and independent healthy-attempt draws simplify a real service considerably. These are six synthetic scenarios, not confidence intervals or AWS measurements.

## Verification

22 core/HTTP tests and 33 browser checks passed. The browser run creates, replays, conflicts, loses an ACK, advances time, recovers without a second effect, changes experiment inputs, exports results, and checks 1440/1024/390 px layouts. No uncaught JavaScript errors or HTTP 5xx responses occurred. These are local checks, not remotely executed CI or production tests.

For an interview, distinguish a request token from an event token, show the database transaction boundaries, then explain why successful-client latency alone can reward a strategy that abandons most users. Also distinguish the worker's eight-claim limit from the experiment's six-attempt client budget.
