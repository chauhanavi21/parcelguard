import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from core import Conflict, OutOfStock, Store, retry_experiment


class OrderTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = Store(Path(self.tmp.name) / "orders.sqlite")

    def test_same_key_replays_identical_result_without_stock_change(self):
        result, replay = self.store.order("case-1", "trail-pack", 2)
        again, replayed = self.store.order("case-1", "trail-pack", 2)
        self.assertFalse(replay)
        self.assertTrue(replayed)
        self.assertEqual(result, again)
        r = self.store.snapshot()
        self.assertEqual(r["summary"]["orders"], 1)
        self.assertTrue(r["verification"]["valid"])

    def test_same_key_different_intent_is_conflict(self):
        self.store.order("case-1", "trail-pack", 1)
        with self.assertRaises(Conflict): self.store.order("case-1", "trail-pack", 2)

    def test_distinct_keys_create_distinct_orders(self):
        a, _ = self.store.order("a", "trail-pack", 1)
        b, _ = self.store.order("b", "trail-pack", 1)
        self.assertNotEqual(a["order_id"], b["order_id"])

    def test_stock_and_event_commit_atomically(self):
        before = self.store.snapshot()
        with self.assertRaises(RuntimeError): self.store.order("fail", "trail-pack", 1, inject_failure=True)
        self.assertEqual(self.store.snapshot(), before)

    def test_lost_ack_redelivers_without_duplicate_business_effect(self):
        self.store.order("a", "trail-pack", 1)
        first = self.store.dispatch("after_delivery")[0]
        self.assertTrue(first["new_effect"])
        self.assertFalse(first["acknowledged"])
        self.store.advance(60)
        second = self.store.dispatch()[0]
        self.assertFalse(second["new_effect"])
        self.assertTrue(second["acknowledged"])
        self.assertEqual(self.store.snapshot()["summary"]["effects"], 1)

    def test_failure_before_delivery_has_no_effect(self):
        self.store.order("a", "trail-pack", 1)
        self.store.dispatch("before_delivery")
        self.assertEqual(self.store.snapshot()["summary"]["effects"], 0)

    def test_failed_delivery_stops_at_attempt_budget(self):
        self.store.order("a", "trail-pack", 1)
        for _ in range(8):
            self.assertEqual(len(self.store.dispatch("before_delivery")), 1)
            self.store.advance(60)
        self.assertEqual(self.store.dispatch(), [])
        state = self.store.snapshot()
        self.assertEqual(state["summary"]["dead_letter"], 1)
        self.assertEqual(state["summary"]["attempts"], 8)
        self.assertEqual(state["summary"]["effects"], 0)

    def test_abandoned_leases_also_stop_at_attempt_budget(self):
        self.store.order("a", "trail-pack", 1)
        for _ in range(8):
            self.assertIsNotNone(self.store.claim())
            self.store.advance(31)
        self.assertIsNone(self.store.claim())
        self.assertEqual(self.store.snapshot()["summary"]["dead_letter"], 1)

    def test_abandoned_claim_expires_and_can_be_recovered(self):
        self.store.order("a", "trail-pack", 1)
        self.assertIsNotNone(self.store.claim())
        self.assertIsNone(self.store.claim())
        self.store.advance(31)
        result = self.store.dispatch()[0]
        self.assertEqual(result["attempt"], 2)
        self.assertTrue(result["acknowledged"])

    def test_concurrent_same_key_only_reserves_once(self):
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(lambda _: self.store.order("concurrent", "trail-pack", 1), range(20)))
        self.assertEqual(len({r[0]["order_id"] for r in results}), 1)
        self.assertEqual(self.store.snapshot()["summary"]["orders"], 1)
        self.assertEqual(self.store.snapshot()["summary"]["replays"], 19)

    def test_concurrent_workers_cannot_duplicate_effects(self):
        for i in range(6): self.store.order(f"key-{i}", "trail-pack", 1)
        with ThreadPoolExecutor(max_workers=6) as pool:
            list(pool.map(lambda _: self.store.dispatch(limit=2), range(6)))
        r = self.store.snapshot()
        self.assertEqual(r["summary"]["effects"], 6)
        self.assertEqual(r["summary"]["pending"], 0)

    def test_out_of_stock_rolls_back(self):
        with self.assertRaises(OutOfStock): self.store.order("too-many", "trail-pack", 121)
        self.assertEqual(self.store.snapshot()["summary"]["orders"], 0)

    def test_invalid_order_and_clock_inputs(self):
        for quantity in [True, 0, -1, 1.5, 1001]:
            with self.subTest(quantity=quantity), self.assertRaises(ValueError): self.store.order("x", "trail-pack", quantity)
        for seconds in [True, 0, 1.2, 3601]:
            with self.assertRaises(ValueError): self.store.advance(seconds)

    def test_committed_idempotency_survives_restart(self):
        result, _ = self.store.order("persist", "trail-pack", 1)
        again, replayed = Store(self.store.path).order("persist", "trail-pack", 1)
        self.assertEqual(result, again)
        self.assertTrue(replayed)

    def test_experiment_is_reproducible_and_bounded(self):
        a = retry_experiment(seed=7, clients=80)
        self.assertEqual(a, retry_experiment(seed=7, clients=80))
        for result in a["results"]:
            self.assertLessEqual(result["attempts"], 6 * 80)
            self.assertLessEqual(result["completed"], 80)

    def test_experiment_refuses_invalid_parameters(self):
        for args in [{"clients": True}, {"capacity": 0}, {"seed": -1}]:
            with self.assertRaises(ValueError): retry_experiment(**args)


if __name__ == "__main__": unittest.main()
