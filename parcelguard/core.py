"""Durable order reservation, transactional outbox, and idempotent local consumer."""
import hashlib
import heapq
import json
import random
import re
import sqlite3
import statistics
import uuid
from contextlib import closing, contextmanager
from pathlib import Path

VERSION = "1.0.0"
MAX_ATTEMPTS = 8
SOURCES = [
    {"title": "AWS: Making retries safe with idempotent APIs", "url": "https://aws.amazon.com/builders-library/making-retries-safe-with-idempotent-APIs/"},
    {"title": "AWS: Timeouts, retries, and backoff with jitter", "url": "https://aws.amazon.com/builders-library/timeouts-retries-and-backoff-with-jitter/"},
]


class Conflict(ValueError): pass
class OutOfStock(ValueError): pass


def canonical(value): return json.dumps(value, sort_keys=True, separators=(",", ":"))
def digest(value): return hashlib.sha256(canonical(value).encode()).hexdigest()


class Store:
    def __init__(self, path):
        self.path = str(path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path)) as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript('''
                PRAGMA foreign_keys=ON;
                CREATE TABLE IF NOT EXISTS inventory(sku TEXT PRIMARY KEY,name TEXT NOT NULL,price_cents INTEGER NOT NULL CHECK(price_cents>0),initial_stock INTEGER NOT NULL,stock INTEGER NOT NULL CHECK(stock>=0));
                CREATE TABLE IF NOT EXISTS orders(id TEXT PRIMARY KEY,sku TEXT NOT NULL REFERENCES inventory(sku),quantity INTEGER NOT NULL CHECK(quantity>0),total_cents INTEGER NOT NULL,stage TEXT NOT NULL,created_ms INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS requests(client TEXT NOT NULL,key TEXT NOT NULL,fingerprint TEXT NOT NULL,response TEXT NOT NULL,PRIMARY KEY(client,key));
                CREATE TABLE IF NOT EXISTS outbox(id TEXT PRIMARY KEY,order_id TEXT UNIQUE NOT NULL REFERENCES orders(id),state TEXT NOT NULL,attempts INTEGER NOT NULL DEFAULT 0,available_ms INTEGER NOT NULL,lease_until_ms INTEGER NOT NULL DEFAULT 0,last_error TEXT NOT NULL DEFAULT '');
                CREATE TABLE IF NOT EXISTS effects(event_id TEXT PRIMARY KEY REFERENCES outbox(id),order_id TEXT UNIQUE NOT NULL REFERENCES orders(id),created_ms INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS delivery_log(seq INTEGER PRIMARY KEY AUTOINCREMENT,event_id TEXT NOT NULL,attempt INTEGER NOT NULL,result TEXT NOT NULL,clock_ms INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY,value INTEGER NOT NULL);
                INSERT OR IGNORE INTO meta VALUES('clock_ms',0);
                INSERT OR IGNORE INTO meta VALUES('replays',0);
                INSERT OR IGNORE INTO inventory VALUES('trail-pack','Trail daypack',7900,120,120);
                INSERT OR IGNORE INTO inventory VALUES('field-bottle','Field bottle',2800,240,240);
                INSERT OR IGNORE INTO inventory VALUES('camp-light','Camp lantern',4600,160,160);
            ''')
            db.commit()

    @contextmanager
    def db(self, write=False):
        db = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA busy_timeout=10000")
        try:
            db.execute("BEGIN IMMEDIATE" if write else "BEGIN")
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally: db.close()

    def order(self, key, sku, quantity, inject_failure=False):
        if not isinstance(key, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", key):
            raise ValueError("Idempotency-Key must be 1–80 letters, digits, dashes, or underscores.")
        if not isinstance(sku, str) or len(sku) > 50: raise ValueError("Invalid SKU.")
        if type(quantity) is not int or not 1 <= quantity <= 1000: raise ValueError("Quantity must be an integer from 1 to 1000.")
        intent = digest({"sku": sku, "quantity": quantity})
        with self.db(True) as db:
            prior = db.execute("SELECT * FROM requests WHERE client='demo-shop' AND key=?", (key,)).fetchone()
            if prior:
                if prior["fingerprint"] != intent: raise Conflict("This idempotency key was already used with different order parameters.")
                db.execute("UPDATE meta SET value=value+1 WHERE key='replays'")
                return json.loads(prior["response"]), True
            item = db.execute("SELECT * FROM inventory WHERE sku=?", (sku,)).fetchone()
            if not item: raise ValueError("Unknown SKU.")
            if item["stock"] < quantity: raise OutOfStock("Not enough stock to reserve this order.")
            now = db.execute("SELECT value FROM meta WHERE key='clock_ms'").fetchone()[0]
            order_id, event_id = uuid.uuid4().hex, uuid.uuid4().hex
            result = {"order_id": order_id, "status": "accepted", "sku": sku, "quantity": quantity, "total_cents": quantity * item["price_cents"]}
            db.execute("UPDATE inventory SET stock=stock-? WHERE sku=?", (quantity, sku))
            db.execute("INSERT INTO orders VALUES(?,?,?,?,?,?)", (order_id, sku, quantity, result["total_cents"], "reserved", now))
            if inject_failure: raise RuntimeError("Injected crash before outbox write")
            db.execute("INSERT INTO outbox(id,order_id,state,available_ms) VALUES(?,?,'pending',?)", (event_id, order_id, now))
            db.execute("INSERT INTO requests VALUES('demo-shop',?,?,?)", (key, intent, canonical(result)))
            return result, False

    def advance(self, seconds):
        if type(seconds) is not int or not 1 <= seconds <= 3600: raise ValueError("Advance by 1–3600 integer seconds.")
        with self.db(True) as db:
            db.execute("UPDATE meta SET value=value+? WHERE key='clock_ms'", (seconds * 1000,))
            return db.execute("SELECT value FROM meta WHERE key='clock_ms'").fetchone()[0]

    def claim(self):
        with self.db(True) as db:
            now = db.execute("SELECT value FROM meta WHERE key='clock_ms'").fetchone()[0]
            db.execute("UPDATE outbox SET state='dead_letter',last_error='Attempt budget exhausted' WHERE attempts>=? AND (state='pending' OR (state='leased' AND lease_until_ms<=?))", (MAX_ATTEMPTS, now))
            row = db.execute("SELECT * FROM outbox WHERE (state='pending' AND available_ms<=?) OR (state='leased' AND lease_until_ms<=?) ORDER BY available_ms,id LIMIT 1", (now, now)).fetchone()
            if not row: return None
            db.execute("UPDATE outbox SET state='leased',attempts=attempts+1,lease_until_ms=? WHERE id=?", (now + 30000, row["id"]))
            return {**dict(row), "attempts": row["attempts"] + 1, "clock_ms": now, "lease_until_ms": now + 30000}

    def consume(self, event):
        with self.db(True) as db:
            inserted = db.execute("INSERT OR IGNORE INTO effects VALUES(?,?,?)", (event["id"], event["order_id"], event["clock_ms"])).rowcount == 1
            if inserted: db.execute("UPDATE orders SET stage='ready_to_pack' WHERE id=?", (event["order_id"],))
            return inserted

    def dispatch(self, fault="none", limit=1):
        if not isinstance(fault, str) or fault not in {"none", "before_delivery", "after_delivery"}: raise ValueError("Unknown failure mode.")
        if type(limit) is not int or not 1 <= limit <= 10: raise ValueError("Worker limit must be 1–10.")
        results = []
        for _ in range(limit):
            event = self.claim()
            if not event: break
            effect_new = False
            if fault != "before_delivery": effect_new = self.consume(event)
            failed = fault != "none"
            result = "failure before consumer" if fault == "before_delivery" else "ack lost after consumer commit" if fault == "after_delivery" else "consumer committed" if effect_new else "duplicate delivery suppressed"
            with self.db(True) as db:
                # A lease can expire while a worker is running. Only its current
                # attempt may acknowledge or reschedule that event.
                owned = db.execute("SELECT 1 FROM outbox WHERE id=? AND state='leased' AND attempts=?", (event["id"], event["attempts"])).fetchone()
                if owned:
                    if failed:
                        cap = min(32000, 1000 * 2 ** min(event["attempts"] - 1, 6))
                        delay = random.Random(f"{event['id']}:{event['attempts']}:42").randint(0, cap)
                        state = "dead_letter" if event["attempts"] >= MAX_ATTEMPTS else "pending"
                        db.execute("UPDATE outbox SET state=?,available_ms=?,last_error=? WHERE id=?", (state, event["clock_ms"] + delay, result, event["id"]))
                    else:
                        db.execute("UPDATE outbox SET state='sent',last_error='' WHERE id=?", (event["id"],))
                db.execute("INSERT INTO delivery_log(event_id,attempt,result,clock_ms) VALUES(?,?,?,?)", (event["id"], event["attempts"], result, event["clock_ms"]))
            results.append({"event_id": event["id"], "attempt": event["attempts"], "result": result, "new_effect": effect_new, "acknowledged": not failed and bool(owned)})
        return results

    def snapshot(self):
        with self.db() as db:
            inventory = [dict(r) for r in db.execute("SELECT * FROM inventory ORDER BY sku")]
            orders = [dict(r) for r in db.execute("SELECT * FROM orders ORDER BY created_ms DESC,id DESC")]
            outbox = [dict(r) for r in db.execute("SELECT * FROM outbox ORDER BY available_ms,id")]
            effects = db.execute("SELECT COUNT(*) FROM effects").fetchone()[0]
            replays = db.execute("SELECT value FROM meta WHERE key='replays'").fetchone()[0]
            clock = db.execute("SELECT value FROM meta WHERE key='clock_ms'").fetchone()[0]
            errors = []
            if len(outbox) != len(orders): errors.append("Order/outbox count mismatch")
            for item in inventory:
                reserved = sum(o["quantity"] for o in orders if o["sku"] == item["sku"])
                if item["initial_stock"] - item["stock"] != reserved: errors.append("Stock conservation failed")
            if effects > len(orders): errors.append("Duplicate business effects")
            return {"model_version": VERSION, "inventory": inventory, "orders": orders, "outbox": outbox,
                    "delivery_log": [dict(r) for r in db.execute("SELECT * FROM delivery_log ORDER BY seq DESC LIMIT 100")],
                    "summary": {"orders": len(orders), "pending": sum(r["state"] in {"pending", "leased"} for r in outbox),
                                "dead_letter": sum(r["state"] == "dead_letter" for r in outbox),
                                "effects": effects, "replays": replays, "attempts": sum(r["attempts"] for r in outbox),
                                "reserved_cents": sum(o["total_cents"] for o in orders)},
                    "clock_ms": clock, "verification": {"valid": not errors, "errors": errors}, "sources": SOURCES,
                    "notes": ["SQLite atomically commits inventory reservation, order, idempotency response, and outbox event.",
                              "A client key replays its original response; the same key with different parameters returns conflict. Keys have no expiry in this prototype.",
                              "Outbox claims have a 30-second logical lease; abandoned claims can be reclaimed after clock advancement.",
                              "Each event has at most eight claims. Exhausted events remain in a dead-letter state for inspection; no automatic redrive is implemented.",
                              "Delivery is at least once. A unique event key and a local consumer transaction prevent duplicate local fulfillment effects. This is not an end-to-end exactly-once guarantee.",
                              "The consumer is a separate SQLite transaction in the same local database, not an external carrier or payment system.",
                              "Logical time and fault controls are explicit lab inputs. No orders, payments, notifications, or cloud requests leave this machine."]}


def retry_experiment(seed=42, clients=120, capacity=15):
    """Bounded discrete-event contention model with fair, keyed service draws.

    Capacity is requests per 100ms slot; healthy success probability is 95%.
    Each strategy gets the same per-client/per-attempt failure draw. Scheduling
    jitter has a separate random stream. This is not a production benchmark.
    """
    for value, name, low, high in [(seed, "seed", 0, 2**32 - 1), (clients, "clients", 10, 1000), (capacity, "capacity", 1, 100)]:
        if type(value) is not int or not low <= value <= high: raise ValueError(f"{name} must be an integer from {low} to {high}.")
    results = []
    for strategy in ["immediate", "exponential", "full_jitter"]:
        queue = [(0, i, 0) for i in range(clients)]
        heapq.heapify(queue)
        slots, attempts, successes, timeline = {}, 0, [], {}
        while queue:
            at, client, attempt = heapq.heappop(queue)
            attempts += 1
            bucket = at // 100
            slots[bucket] = slots.get(bucket, 0) + 1
            timeline[bucket] = timeline.get(bucket, 0) + 1
            healthy_draw = random.Random(f"service:{seed}:{client}:{attempt}").random()
            success = slots[bucket] <= capacity and healthy_draw >= .05
            if success:
                successes.append(at + 25)
            elif attempt < 5:
                bound = min(3200, 200 * 2 ** attempt)
                wait = 1 if strategy == "immediate" else bound if strategy == "exponential" else random.Random(f"jitter:{seed}:{client}:{attempt}").randint(1, bound)
                heapq.heappush(queue, (at + wait, client, attempt + 1))
        ordered = sorted(successes)
        results.append({"strategy": strategy, "attempts": attempts, "completed": len(successes), "clients": clients,
                        "amplification": attempts / clients, "peak_attempts_per_slot": max(timeline.values()),
                        "completion_rate": len(successes) / clients,
                        "p95_success_latency_ms": ordered[max(0, (95 * len(ordered) + 99) // 100 - 1)] if ordered else None,
                        "timeline": [{"ms": bucket * 100, "attempts": count} for bucket, count in sorted(timeline.items())]})
    return {"seed": seed, "clients": clients, "capacity_per_100ms": capacity, "max_attempts": 6,
            "model_version": VERSION, "results": results,
            "note": "Synthetic synchronized contention model. p95 is conditional on successful clients; failed clients are reported separately. Jitter results are workload-dependent, not a universal guarantee."}
