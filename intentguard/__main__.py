"""Dependency-free offline demo: python -m intentguard demo."""

import argparse
import json

from .demo import DemoCloud, seed
from .service import Service
from .storage import SQLiteStore


def main():
    parser = argparse.ArgumentParser(description="IntentGuard local demo")
    parser.add_argument("command", choices=["demo"])
    parser.add_argument("--db", default="data/intentguard.db")
    args = parser.parse_args()
    service = Service(SQLiteStore(args.db), DemoCloud())
    seed(service)
    service.dispatch({"operation": "verify_all"})
    results = []
    for resource in service.cloud.discover():
        decision = service.request(resource["resource_id"])
        results.append(
            {
                "resource": resource["name"],
                "decision": decision["decision"],
                "reason": decision["reason"],
            }
        )
    print(json.dumps({"mode": "SIMULATED / DRY RUN", "results": results}, indent=2))


if __name__ == "__main__":
    main()
