"""Synthetic resources and telemetry, clearly separated from AWS."""

from datetime import timedelta

from .models import iso


class DemoCloud:
    def __init__(self):
        self.resources = [
            {
                "resource_id": "i-00000000000000001",
                "name": "Standby backup",
                "state": "running",
                "root_device_type": "ebs",
                "autoscaling": False,
                "tags": {"IntentGuardManaged": "true"},
            },
            {
                "resource_id": "i-00000000000000002",
                "name": "Disposable test",
                "state": "running",
                "root_device_type": "ebs",
                "autoscaling": False,
                "tags": {"IntentGuardManaged": "true", "IntentGuardDisposable": "true"},
            },
            {
                "resource_id": "i-00000000000000003",
                "name": "Expired backup",
                "state": "running",
                "root_device_type": "ebs",
                "autoscaling": False,
                "tags": {"IntentGuardManaged": "true"},
            },
            {
                "resource_id": "i-00000000000000004",
                "name": "Undeclared server",
                "state": "running",
                "root_device_type": "ebs",
                "autoscaling": False,
                "tags": {},
            },
        ]

    def discover(self):
        return self.resources

    def get(self, rid):
        return next((r for r in self.resources if r["resource_id"] == rid), None)

    def metrics(self, rid, now):
        return [{"timestamp": iso(now - timedelta(minutes=m)), "maximum": 2.0} for m in (15, 10, 5)]

    def stop(self, rid):
        raise ValueError("Local demo cannot execute AWS actions")


def seed(service):
    now = service.clock()
    for resource in service.cloud.discover()[:3]:
        if service.store.get(resource["resource_id"]):
            continue
        item = {
            "resource_id": resource["resource_id"],
            "owner": "team-demo",
            "intent_type": "disposable_test"
            if resource["name"] == "Disposable test"
            else "warm_standby",
            "reason": resource["name"],
            "expires_at": iso(now + timedelta(days=7)),
            "cpu_max_percent": 10,
        }
        saved = service.register(item)
        if resource["name"] == "Expired backup":
            saved["expires_at"] = iso(now - timedelta(hours=1))
            service.store.save(saved, saved["version"])
        service.verify_one(resource["resource_id"])
