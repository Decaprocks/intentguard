"""Use cases shared by the dashboard, CLI and Lambda handler."""

from uuid import uuid4

from .models import declaration, iso, utcnow
from .policy import evaluate
from .verifier import verify


class Service:
    def __init__(self, store, cloud, clock=utcnow, execution_enabled=False, notifier=None):
        self.store, self.cloud, self.clock = store, cloud, clock
        self.execution_enabled, self.notifier = execution_enabled, notifier

    def event(self, kind, **fields):
        event = {"event_id": str(uuid4()), "timestamp": iso(self.clock()), "kind": kind, **fields}
        self.store.audit(event)
        return event

    def register(self, payload):
        item = declaration(payload, self.clock())
        resource = self.cloud.get(item["resource_id"])
        if not resource or resource.get("tags", {}).get("IntentGuardManaged") != "true":
            raise ValueError("Resource must exist and have IntentGuardManaged=true")
        old = self.store.get(item["resource_id"])
        if old and old["owner"] != item["owner"]:
            raise ValueError(
                "Renewal cannot change owner; administrative transfer is outside this MVP"
            )
        # Audit first: a logging outage prevents registry mutation.
        self.event("registration_requested", resource_id=item["resource_id"], owner=item["owner"])
        saved = self.store.save(item, old["version"] if old else 0)
        self.event("registered", resource_id=item["resource_id"], version=saved["version"])
        return saved

    def verify_one(self, rid):
        item = self.store.get(rid)
        if not item:
            raise ValueError("Register an intent first")
        now = self.clock()
        updated = verify(item, self.cloud.metrics(rid, now), now)
        self.event("verification_requested", resource_id=rid, version=item["version"])
        updated = self.store.save(updated, item["version"])
        self.event(
            "verified",
            resource_id=rid,
            trust_state=updated["trust_state"],
            reason=updated["verification_reason"],
        )
        if (
            updated["trust_state"] in {"stale", "contradicted"}
            and updated["trust_state"] != item["trust_state"]
            and self.notifier
        ):
            try:
                self.notifier(updated)
            except Exception as exc:
                self.event("notification_failed", resource_id=rid, error_type=type(exc).__name__)
        return updated

    def request(self, rid, action="stop", execute=False):
        if not isinstance(execute, bool):
            raise ValueError("execute must be a boolean")
        if execute and not self.execution_enabled:
            raise ValueError("Execution is disabled on this backend")
        # Re-read authoritative registry/resource state on every request.
        intent, resource = self.store.get(rid), self.cloud.get(rid)
        decision = evaluate(intent, resource, self.clock(), action)
        record = self.event(
            "decision",
            resource_id=rid,
            action=action,
            execute_requested=execute,
            executed=False,
            intent_version=intent["version"] if intent else None,
            **decision,
        )
        if execute and decision["decision"] == "ALLOW":
            # Check for concurrent renewal before the side effect; IAM tags add an independent guard.
            latest = self.store.get(rid)
            if not latest or latest["version"] != intent["version"]:
                raise ValueError("Intent changed during evaluation; retry a fresh dry run")
            try:
                self.cloud.stop(rid)
            except Exception as exc:
                self.event(
                    "execution_failed_or_unknown",
                    resource_id=rid,
                    decision_event=record["event_id"],
                    error_type=type(exc).__name__,
                )
                raise
            self.event("stop_requested", resource_id=rid, decision_event=record["event_id"])
            record = {**record, "executed": True}
        return record

    def dispatch(self, event):
        op = event.get("operation")
        if op == "discover":
            return self.cloud.discover()
        if op == "list_intents":
            return self.store.list()
        if op == "history":
            return self.store.history()
        if op == "register":
            return self.register(event["intent"])
        if op == "verify":
            return self.verify_one(event["resource_id"])
        if op == "verify_all":
            results = []
            for item in self.store.list():
                try:
                    results.append(self.verify_one(item["resource_id"]))
                except Exception as exc:
                    results.append(
                        {"resource_id": item["resource_id"], "error": type(exc).__name__}
                    )
            return results
        if op == "request":
            return self.request(
                event["resource_id"], event.get("action", "stop"), event.get("execute", False)
            )
        if op == "optimize":
            # The built-in optimizer only proposes stops; execution stays a separate explicit request.
            return [self.request(r["resource_id"]) for r in self.cloud.discover()]
        raise ValueError("Unknown operation")
