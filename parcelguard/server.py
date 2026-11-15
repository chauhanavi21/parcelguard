import argparse
from pathlib import Path

from core import VERSION, Conflict, OutOfStock, Store, retry_experiment
from httpkit import Fault, Handler, Reply, Server, serve


class API(Handler):
    def get_api(self, path, query):
        if path == "/api/health": return {"status": "ok", "project": "ParcelGuard", "version": VERSION}
        if path == "/api/workspace": return self.server.store.snapshot()
        raise Fault(404, "Route not found.")

    def post_api(self, path, body):
        if path == "/api/orders":
            if set(body) != {"sku", "quantity"}: raise Fault(400, "Provide sku and quantity only.")
            try: response, replayed = self.server.store.order(self.headers.get("Idempotency-Key"), **body)
            except Conflict as exc: raise Fault(409, str(exc)) from None
            except OutOfStock as exc: raise Fault(409, str(exc)) from None
            return Reply({**response, "replayed": replayed}, 200 if replayed else 201)
        if path == "/api/dispatch":
            if set(body) - {"fault", "limit"}: raise Fault(400, "Unknown worker setting.")
            return {"deliveries": self.server.store.dispatch(**body)}
        if path == "/api/advance":
            if set(body) != {"seconds"}: raise Fault(400, "Provide seconds only.")
            return {"clock_ms": self.server.store.advance(body["seconds"])}
        if path == "/api/experiment":
            if set(body) - {"seed", "clients", "capacity"}: raise Fault(400, "Unknown experiment setting.")
            return retry_experiment(**body)
        raise Fault(404, "Route not found.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ParcelGuard local failure laboratory")
    parser.add_argument("--port", type=int, default=8772)
    parser.add_argument("--db", type=Path, default=Path(__file__).parent / "runtime/orders.sqlite")
    args = parser.parse_args()
    serve(Server(args.port, API, Path(__file__).parent, Store(args.db)))
