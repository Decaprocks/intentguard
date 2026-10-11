from datetime import timedelta

import pytest

from intentguard.models import declaration, iso, timestamp
from intentguard.policy import evaluate
from intentguard.storage import Conflict, SQLiteStore
from intentguard.verifier import verify


def points(now, values=(2, 3, 1)):
    return [
        {"timestamp": iso(now - timedelta(minutes=m)), "maximum": v}
        for m, v in zip((15, 10, 5), values, strict=True)
    ]


def test_end_to_end_disposable_dry_run(service, payload):
    assert service.register(payload)["trust_state"] == "unverified"
    assert service.request(payload["resource_id"])["decision"] == "REVIEW"
    assert service.verify_one(payload["resource_id"])["trust_state"] == "verified"
    result = service.request(payload["resource_id"])
    assert result["decision"] == "ALLOW" and result["executed"] is False
    assert any(e["kind"] == "decision" for e in service.store.history())


@pytest.mark.parametrize("kind", ["warm_standby", "compliance_replica", "burst_buffer"])
def test_protected_purpose_blocks_even_before_verification(service, payload, kind):
    service.register({**payload, "intent_type": kind})
    assert service.request(payload["resource_id"])["decision"] == "BLOCK"


def test_no_intent_requires_review(service):
    assert service.request("i-00000000000000004")["decision"] == "REVIEW"


def test_expired_intent_never_allows_stop(service, payload, now):
    item = service.register(payload)
    item.update(
        expires_at=iso(now - timedelta(seconds=1)), trust_state="verified", verified_at=iso(now)
    )
    service.store.save(item, item["version"])
    assert service.verify_one(payload["resource_id"])["trust_state"] == "stale"
    assert service.request(payload["resource_id"])["decision"] == "REVIEW"


@pytest.mark.parametrize(
    "updates",
    [
        {"trust_state": "verified"},
        {"cpu_max_percent": float("nan")},
        {"cpu_max_percent": float("inf")},
        {"cpu_max_percent": True},
        {"cpu_max_percent": -1},
        {"cpu_max_percent": 101},
        {"expires_at": "2026-10-12T00:00:00"},
        {"intent_type": "production"},
        {"resource_id": "arbitrary"},
        {"owner": " "},
        {"reason": ""},
    ],
)
def test_invalid_or_forged_declarations_rejected(payload, now, updates):
    with pytest.raises(ValueError):
        declaration({**payload, **updates}, now)


@pytest.mark.parametrize("offset", [-1, 0, 91])
def test_expiry_bounds(payload, now, offset):
    with pytest.raises(ValueError):
        declaration({**payload, "expires_at": iso(now + timedelta(days=offset))}, now)


def test_owner_cannot_be_changed_on_renewal(service, payload):
    service.register(payload)
    with pytest.raises(ValueError, match="change owner"):
        service.register({**payload, "owner": "other"})


def test_renewal_resets_verification(service, payload):
    service.register(payload)
    service.verify_one(payload["resource_id"])
    renewed = service.register(payload)
    assert renewed["trust_state"] == "unverified" and renewed["verified_at"] is None


def test_store_survives_restart_and_rejects_stale_write(tmp_path, payload, now):
    path = tmp_path / "registry.db"
    store = SQLiteStore(path)
    saved = store.save(declaration(payload, now))
    other = SQLiteStore(path)
    assert other.get(payload["resource_id"]) == saved
    other.save(saved, saved["version"])
    with pytest.raises(Conflict):
        store.save(saved, saved["version"])
    with pytest.raises(Conflict):
        store.save(saved, 0)


@pytest.mark.parametrize("evidence", ["missing", "old", "future", "duplicate", "gaps", "invalid"])
def test_bad_metric_evidence_does_not_verify(payload, now, evidence):
    samples = points(now)
    if evidence == "missing":
        samples = []
    elif evidence == "old":
        samples = points(now - timedelta(hours=1))
    elif evidence == "future":
        samples = points(now + timedelta(hours=1))
    elif evidence == "duplicate":
        samples = [samples[0]] * 3
    elif evidence == "gaps":
        samples[0]["timestamp"] = iso(now - timedelta(minutes=29))
    elif evidence == "invalid":
        samples[0]["maximum"] = float("nan")
    assert verify(declaration(payload, now), samples, now)["trust_state"] == "unverified"


def test_sustained_contradiction_latches_until_renewal(service, payload, now):
    item = service.register(payload)
    contradicted = verify(item, points(now, (60, 70, 80)), now)
    assert contradicted["trust_state"] == "contradicted"
    contradicted = service.store.save(contradicted, item["version"])
    assert verify(contradicted, points(now), now)["trust_state"] == "contradicted"
    assert service.request(payload["resource_id"])["decision"] == "REVIEW"
    renewed = service.register(payload)
    assert service.verify_one(renewed["resource_id"])["trust_state"] == "verified"


def test_burst_buffer_not_verified_using_idle_cpu(payload, now):
    item = declaration({**payload, "intent_type": "burst_buffer"}, now)
    assert verify(item, points(now), now)["trust_state"] == "unverified"


def test_mixed_metrics_require_more_observation(payload, now):
    assert (
        verify(declaration(payload, now), points(now, (2, 80, 3)), now)["trust_state"]
        == "unverified"
    )


@pytest.mark.parametrize("offset", [-11, 1])
def test_verification_freshness(service, payload, now, offset):
    item = service.register(payload)
    item.update(trust_state="verified", verified_at=iso(now + timedelta(minutes=offset)))
    service.store.save(item, item["version"])
    assert service.request(payload["resource_id"])["decision"] == "REVIEW"


@pytest.mark.parametrize(
    "mutation", ["missing_tag", "autoscaling", "instance_store", "stopped", "missing"]
)
def test_resource_guards(service, payload, mutation):
    service.register(payload)
    service.verify_one(payload["resource_id"])
    r = service.cloud.get(payload["resource_id"])
    if mutation == "missing_tag":
        r["tags"].pop("IntentGuardDisposable")
    elif mutation == "autoscaling":
        r["autoscaling"] = True
    elif mutation == "instance_store":
        r["root_device_type"] = "instance-store"
    elif mutation == "stopped":
        r["state"] = "stopped"
    else:
        service.cloud.resources.remove(r)
    assert service.request(payload["resource_id"])["decision"] != "ALLOW"


def test_resource_id_mismatch_blocks(service, payload, now):
    assert (
        evaluate(declaration(payload, now), service.cloud.resources[0], now)["decision"] == "BLOCK"
    )


def test_termination_not_supported(service, payload):
    assert service.request(payload["resource_id"], action="terminate")["decision"] == "BLOCK"


def test_execution_off_by_default(service, payload):
    with pytest.raises(ValueError, match="disabled"):
        service.request(payload["resource_id"], execute=True)


def test_string_execute_rejected(service, payload):
    with pytest.raises(ValueError, match="boolean"):
        service.request(payload["resource_id"], execute="false")


def test_live_stop_only_after_allowed_decision_and_audit(service, payload, monkeypatch):
    service.execution_enabled = True
    service.register(payload)
    service.verify_one(payload["resource_id"])
    stopped = []

    def stop(rid):
        assert service.store.history()[0]["kind"] == "decision"
        stopped.append(rid)

    monkeypatch.setattr(service.cloud, "stop", stop)
    assert service.request(payload["resource_id"], execute=True)["executed"] is True
    assert stopped == [payload["resource_id"]]
    assert service.store.history()[0]["kind"] == "stop_requested"


def test_blocked_request_never_calls_stop(service, payload, monkeypatch):
    service.execution_enabled = True
    service.register({**payload, "intent_type": "warm_standby"})
    monkeypatch.setattr(service.cloud, "stop", lambda _: pytest.fail("Protected resource stopped"))
    assert service.request(payload["resource_id"], execute=True)["executed"] is False


def test_audit_failure_prevents_stop(service, payload, monkeypatch):
    service.register(payload)
    service.verify_one(payload["resource_id"])
    service.execution_enabled = True
    monkeypatch.setattr(service.cloud, "stop", lambda _: pytest.fail("Stop must not occur"))

    def unavailable(_):
        raise RuntimeError("Storage unavailable")

    monkeypatch.setattr(service.store, "audit", unavailable)
    with pytest.raises(RuntimeError):
        service.request(payload["resource_id"], execute=True)


def test_aws_error_logged_as_failed_or_unknown(service, payload, monkeypatch):
    service.register(payload)
    service.verify_one(payload["resource_id"])
    service.execution_enabled = True

    def fail(_):
        raise RuntimeError("network timeout")

    monkeypatch.setattr(service.cloud, "stop", fail)
    with pytest.raises(RuntimeError):
        service.request(payload["resource_id"], execute=True)
    assert service.store.history()[0]["kind"] == "execution_failed_or_unknown"


def test_notification_on_state_transition_only(service, payload, now):
    item = service.register(payload)
    item["expires_at"] = iso(now - timedelta(minutes=1))
    service.store.save(item, item["version"])
    sent = []
    service.notifier = sent.append
    service.verify_one(payload["resource_id"])
    service.verify_one(payload["resource_id"])
    assert len(sent) == 1 and sent[0]["trust_state"] == "stale"


def test_verify_all_isolates_one_resource_failure(service, payload, monkeypatch):
    service.register(payload)
    service.register({**payload, "resource_id": "i-00000000000000001"})
    original = service.cloud.metrics

    def metrics(rid, now):
        if rid == payload["resource_id"]:
            raise RuntimeError("CloudWatch unavailable")
        return original(rid, now)

    monkeypatch.setattr(service.cloud, "metrics", metrics)
    result = service.dispatch({"operation": "verify_all"})
    assert len(result) == 2
    assert sum("error" in r for r in result) == 1


def test_timezone_required():
    with pytest.raises(ValueError):
        timestamp("2026-10-11T12:00:00")


def test_optimizer_proposes_only_dry_runs(service, payload, monkeypatch):
    service.register(payload)
    service.verify_one(payload["resource_id"])
    service.execution_enabled = True
    monkeypatch.setattr(service.cloud, "stop", lambda _: pytest.fail("Optimizer must not execute"))
    plan = service.dispatch({"operation": "optimize"})
    assert len(plan) == 4
    assert sum(r["decision"] == "ALLOW" for r in plan) == 1
    assert all(not r["executed"] for r in plan)


def test_concurrent_renewal_prevents_execution(service, payload, monkeypatch):
    service.register(payload)
    service.verify_one(payload["resource_id"])
    service.execution_enabled = True
    original = service.store.get
    reads = 0

    def changing_get(rid):
        nonlocal reads
        reads += 1
        item = original(rid)
        if reads == 2:
            item = {**item, "version": item["version"] + 1}
        return item

    monkeypatch.setattr(service.store, "get", changing_get)
    monkeypatch.setattr(
        service.cloud, "stop", lambda _: pytest.fail("Changed intent must not execute")
    )
    with pytest.raises(ValueError, match="changed during"):
        service.request(payload["resource_id"], execute=True)
