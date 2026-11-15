from httpcase import BoundaryCase


class HTTPTests(BoundaryCase):
    def order(self, key="a", quantity=1):
        return self.request("POST", "/api/orders", {"sku":"trail-pack", "quantity":quantity}, {"Idempotency-Key":key})

    def test_created_replayed_and_conflicting_status(self):
        status, _, first = self.order()
        self.assertEqual(status, 201)
        status, _, second = self.order()
        self.assertEqual(status, 200)
        self.assertTrue(second["replayed"])
        self.assertEqual(first["order_id"], second["order_id"])
        self.assertEqual(self.order(quantity=2)[0], 409)

    def test_missing_key_and_invalid_quantity(self):
        self.assertEqual(self.request("POST", "/api/orders", {"sku":"trail-pack", "quantity":1})[0], 400)
        self.assertEqual(self.order(quantity=True)[0], 400)
        self.assertEqual(self.order(quantity=121)[0], 409)

    def test_lost_ack_then_recovery_over_http(self):
        self.order()
        first = self.request("POST", "/api/dispatch", {"fault":"after_delivery"})[2]["deliveries"][0]
        self.assertTrue(first["new_effect"])
        self.request("POST", "/api/advance", {"seconds":60})
        second = self.request("POST", "/api/dispatch", {})[2]["deliveries"][0]
        self.assertFalse(second["new_effect"])
        result = self.request("GET", "/api/workspace")[2]
        self.assertEqual(result["summary"]["effects"], 1)
        self.assertEqual(result["summary"]["pending"], 0)

    def test_invalid_worker_settings_return_400(self):
        for body in [{"fault":[]}, {"fault":{}}, {"limit":True}, {"unexpected":1}]:
            self.assertEqual(self.request("POST", "/api/dispatch", body)[0], 400)

    def test_invalid_json_and_foreign_origin(self):
        self.assertEqual(self.request("POST", "/api/experiment", raw='{"seed":Infinity}', headers={"Content-Type":"application/json"})[0], 400)
        self.assertEqual(self.request("POST", "/api/advance", {"seconds":60}, {"Origin":"https://example.com"})[0], 403)

    def test_bounded_experiment_over_http(self):
        status, _, result = self.request("POST", "/api/experiment", {"clients":30, "capacity":5, "seed":7})
        self.assertEqual(status, 200)
        self.assertTrue(all(row["attempts"]<=180 for row in result["results"]))

    def test_unexpected_host_header_rejected(self):
        self.assertEqual(self.request("GET", "/api/health", headers={"Host": "evil.example"})[0], 403)
        self.assertEqual(self.request("GET", "/api/health", headers={"Host": "evil.example:%d" % self.server.server_port})[0], 403)
        self.assertEqual(self.request("GET", "/api/health", headers={"Host": "localhost:%d" % self.server.server_port})[0], 200)
        self.assertEqual(self.request("GET", "/api/health")[0], 200)

    def test_empty_post_body_is_bad_request_not_too_large(self):
        status, _, body = self.request("POST", "/api/health", raw="", headers={"Content-Type": "application/json"})
        self.assertEqual(status, 400)
        self.assertIn("{}", body["error"])
