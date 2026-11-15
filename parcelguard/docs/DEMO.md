# ParcelGuard: three-minute walkthrough

From `parcelguard`, run `python server.py` and open http://127.0.0.1:8772. For a fresh isolated run while the original app is open, use an unused database filename:

```powershell
python server.py --port 8782 --db runtime/recruiter-demo-01.sqlite
```

Open http://127.0.0.1:8782 for that command. Existing files retain their orders; change the filename to repeat from empty state.

## 0:00–0:40 — Reserve once, replay the response

Choose Trail daypack, quantity 2, and key `demo-order-01`. Reserve the order. On a fresh database, there is one order and stock is 118.

Submit again with the same key and quantity. The response says REPLAY; orders and stock do not change. Change the quantity to 3 while keeping the key, then submit: changed intent returns a conflict. Set quantity back to 2.

“A request key expresses the caller's intent. It is not a hash that silently treats every identical purchase as a duplicate.”

## 0:40–1:35 — Lose an acknowledgement

Choose **Lose ACK after consumer commits** and deliver one due event. On an otherwise empty run there is one consumer effect and one event awaiting acknowledgement.

Advance 60 seconds, select healthy delivery, and deliver again. The log shows duplicate delivery suppressed. Effects stays at 1, the outbox is sent, and the claim count is 2.

Explain the separate transactions: claim, consumer effect, and acknowledgement. If the ACK disappears after the consumer commit, the event must be retried even though its effect already happened. The consumer event key suppresses that repeated local effect.

## 1:35–2:25 — Compare retry strategies

Run the default experiment: 120 clients, capacity 15 per 100 ms, seed 42. Immediate retry completes 14/120, exponential backoff 87/120, and full jitter 120/120 in this synthetic model. Total attempts are 650, 506, and 372 respectively.

“Immediate retry's 25 ms p95 only includes its 14 successful clients. It hides 106 failures if shown alone.”

Change clients to 40 and capacity to 100, retaining seed 42. All three strategies complete all clients with 43 attempts each; immediate retry has the lowest successful-client p95. The result depends on contention rather than establishing a universal winner.

## 2:25–3:00 — Show the evidence and boundary

Export the pipeline and experiment report. Open `artifacts/retry-study.json` for the two workloads across three seeds, and `tests/test_core.py` for rollback, concurrency, lease recovery, and attempt exhaustion.

The worker has eight claims per event; the separate simulation has six attempts per client. Both are explicit model choices. The consumer and outbox share one local database; this demonstration does not prove exactly-once external fulfillment. No real order, payment, or cloud request is made by the pipeline.
