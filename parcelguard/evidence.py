"""Generate order failure evidence and a paired, seeded retry study."""
import json
import tempfile
from pathlib import Path
from core import Conflict, Store, retry_experiment


def generate():
    with tempfile.TemporaryDirectory() as temporary:
        store = Store(Path(temporary) / "evidence.sqlite")
        original, _ = store.order("evidence-order", "trail-pack", 2)
        replay, replayed = store.order("evidence-order", "trail-pack", 2)
        try: store.order("evidence-order", "trail-pack", 3)
        except Conflict: conflict = True
        else: conflict = False
        before = store.snapshot()
        try: store.order("atomic-failure", "camp-light", 1, inject_failure=True)
        except RuntimeError: pass
        rollback = store.snapshot() == before
        lost_ack = store.dispatch("after_delivery")[0]
        after_loss = store.snapshot()["summary"]
        store.advance(60)
        recovered = store.dispatch()[0]
        final = store.snapshot()
        checks = {"identical_replay":replayed and replay==original, "changed_intent_conflicts":conflict,
                  "injected_failure_rolled_back_exactly":rollback, "consumer_committed_before_lost_ack":lost_ack["new_effect"] and not lost_ack["acknowledged"],
                  "retry_deduplicated":not recovered["new_effect"] and recovered["acknowledged"],
                  "one_order_one_effect":final["summary"]["orders"]==final["summary"]["effects"]==1,
                  "stock_conserved":final["verification"]["valid"] and next(i for i in final["inventory"] if i["sku"]=="trail-pack")["stock"]==118}
        assert all(checks.values()), checks
        evidence = {"checks":checks, "after_lost_ack":after_loss, "final":final,
                    "limits":"Single local client scope; consumer and outbox use separate transactions in one SQLite database. Random order/event IDs vary. No external delivery."}
    study = {"scenarios":[], "limits":"Synthetic synchronized workload; paired per-client/attempt service draws, separate jitter stream. Three seeds per workload, not production measurements. Success p95 excludes failed clients."}
    for name, clients, capacity in [("contention",120,15),("spare_capacity",40,100)]:
        for seed in [7,42,2026]:
            study["scenarios"].append({"name":name, **retry_experiment(seed,clients,capacity)})
    root = Path(__file__).resolve().parent / "artifacts"
    root.mkdir(exist_ok=True)
    (root / "order-evidence.json").write_text(json.dumps(evidence,indent=2),encoding="utf-8")
    (root / "retry-study.json").write_text(json.dumps(study,indent=2),encoding="utf-8")
    return {"checks":checks, "default_experiment":retry_experiment()}


if __name__ == "__main__": print(json.dumps(generate(), indent=2))
