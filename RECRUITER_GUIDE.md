# Presenting ParcelGuard

ParcelGuard demonstrates safe retries around ambiguous completion: the first operation may have committed even when its response disappears. It pairs a working local order/outbox pipeline with a reproducible retry contention model.

## A short introduction

“I built a local idempotent order pipeline based on the public AWS Builders' Library. Reservation, order, saved response, and outbox event commit together. I can lose the acknowledgement after the consumer commits, then retry and show one local effect. A separate experiment compares completion, retry amplification, and successful-client latency under contention and spare capacity.”

## Draft résumé bullets

- Built a Python/SQLite order reliability lab with client-scoped idempotency keys, intent-conflict detection, a transactional outbox, leased claims, bounded retries, and consumer deduplication; verified 22 core/HTTP tests and 33 browser checks.
- Designed paired, seeded retry experiments across two synthetic workloads; measured completion, retry amplification, and conditional latency, showing why low successful-client latency can hide a high failure rate.

## Evidence to show

| Claim | Evidence |
|---|---|
| Replay without another reservation | [Core and HTTP tests](parcelguard/tests/test_core.py) and the live order replay |
| Lost-ACK recovery without a second local effect | [Order evidence](parcelguard/artifacts/order-evidence.json) and the delivery log |
| Bounded retry load | [Lease/attempt tests](parcelguard/tests/test_core.py) and [retry study](parcelguard/artifacts/retry-study.json) |
| Workload-dependent conclusions | [Contention and spare-capacity findings](parcelguard/docs/FINDINGS.md) |
| Working controls and exports | [Browser report](parcelguard/artifacts/browser-checks.json) |

Use the [three-minute walkthrough](parcelguard/docs/DEMO.md). Be ready to distinguish the client request key from the consumer event key, and explain why a dead letter may already have a committed effect if its last acknowledgement was lost.

## Repository and source package

Use this **`amazon` folder as the repository root** so `.github/workflows/verify.yml` is at the top. Python 3.11+ runs the app without runtime packages or AWS credentials. Optional browser setup is documented in the app README.

```powershell
python tools/package.py
python tools/package.py --check
```

This creates `dist/parcelguard-source.zip` with a per-file SHA-256 manifest. An explicit file list includes source, documentation, screenshot, tests, and public demo evidence; runtime databases, logs, environments, caches, and raw browser output are excluded.

GitHub Actions runs Windows/Linux core and HTTP tests, Chromium/Firefox/WebKit workflows, accessibility and mobile lab checks, verified source packaging, and the interactive Pages deployment. The link below shows actual remote run status; checked-in reports record local runs.

The consumer uses a separate transaction in the same SQLite database. Unique event IDs prevent repeated local effects in the tested model; this is not a global exactly-once delivery guarantee, a real payment/carrier integration, or an AWS performance benchmark. This independent portfolio project is not affiliated with Amazon.

## Published review

[Live browser demo](https://chauhanavi21.github.io/parcelguard/) | [Short recording](https://chauhanavi21.github.io/parcelguard/watch.html) | [CI runs](https://github.com/chauhanavi21/parcelguard/actions). Review the [release evidence](parcelguard/docs/RELEASE.md) for browser, accessibility, mobile and historical-data checks. The Pages demo runs temporary Python/SQLite state in-browser; use local HTTP mode to assess server-session and concurrency behavior.
