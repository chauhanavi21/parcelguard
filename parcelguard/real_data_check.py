"""Replay a pinned historical retail-line fixture; no network or runtime DB touched."""
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import tempfile

from core import Store, Conflict

ROOT = Path(__file__).resolve().parent


def main():
    fixture = ROOT / "data/retail-lines.csv"
    provenance = json.loads((ROOT / "data/provenance.json").read_text())
    assert hashlib.sha256(fixture.read_bytes()).hexdigest() == provenance["fixture_sha256"]
    rows = list(csv.DictReader(fixture.open(encoding="utf-8", newline="")))
    products = {}
    for row in rows:
        row["quantity"] = int(row["quantity"])
        row["unit_price_pence"] = int(row["unit_price_pence"])
        row["sku"] = f"uci-{row['stock_code']}-{row['unit_price_pence']}"
        products.setdefault(row["sku"], {"price": row["unit_price_pence"], "stock": 10})["stock"] += row["quantity"]
    with tempfile.TemporaryDirectory() as temporary:
        store = Store(Path(temporary) / "real.sqlite")
        with store.db(True) as db:
            for sku, item in products.items():
                db.execute("INSERT INTO inventory VALUES(?,?,?,?,?)", (sku, sku, item["price"], item["stock"], item["stock"]))
        expected = 0
        for row in rows:
            key = f"uci-row-{row['source_row']}"
            response, replay = store.order(key, row["sku"], row["quantity"])
            assert not replay
            repeated, replay = store.order(key, row["sku"], row["quantity"])
            assert replay and response == repeated
            expected += row["quantity"] * row["unit_price_pence"]
        conflicts = 0
        for row in rows[:10]:
            try:
                store.order(f"uci-row-{row['source_row']}", row["sku"], row["quantity"] + 1)
            except Conflict:
                conflicts += 1
        assert conflicts == 10
        # Every tenth initial delivery loses its ACK after the consumer commits.
        for index in range(len(rows)):
            store.dispatch("after_delivery" if index % 10 == 0 else "none")
        store.advance(60)
        while store.dispatch("none", limit=10):
            pass
        state = store.snapshot()
        assert state["verification"]["valid"]
        assert state["summary"]["orders"] == state["summary"]["effects"] == len(rows)
        assert state["summary"]["pending"] == state["summary"]["dead_letter"] == 0
        assert state["summary"]["reserved_cents"] == expected
        assert state["summary"]["attempts"] == len(rows) + 20
        result = {"checked_at": datetime.now(timezone.utc).isoformat(), "dataset": provenance["dataset"],
                  "fixture_sha256": provenance["fixture_sha256"], "passed": True,
                  "line_orders": len(rows), "distinct_product_price_variants": len(products),
                  "replays": state["summary"]["replays"], "changed_intent_conflicts": conflicts,
                  "effects": state["summary"]["effects"], "claims": state["summary"]["attempts"],
                  "reserved_pence": expected, "pending": 0,
                  "scope": "Each historical invoice line becomes an order, not a complete invoice. GBP pence are preserved. Inventory is a constructed sufficient-stock fixture. Duplicate requests and 20 lost acknowledgements are injected, not observed in the source. No production retry-performance inference."}
    (ROOT / "artifacts/real-data-checks.json").write_text(json.dumps(result, indent=2)+"\n", encoding="utf-8")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
