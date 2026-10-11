"""Fail-closed stop policy. No resource or metric mutations here."""

from datetime import timedelta

from .models import PROTECTED, timestamp


def evaluate(intent, resource, now, action="stop"):
    def result(decision, reason):
        return {"decision": decision, "reason": reason}

    if action != "stop":
        return result("BLOCK", "Only stop is supported; termination and rightsizing are disabled")
    if not resource or resource.get("state") != "running":
        return result("REVIEW", "Resource is missing or not running")
    if not intent:
        return result("REVIEW", "No intent declaration; idle CPU alone is not permission to stop")
    if intent["resource_id"] != resource["resource_id"]:
        return result("BLOCK", "Declaration does not match the requested resource")
    if timestamp(intent["expires_at"]) <= now:
        return result("REVIEW", "Declaration expired; owner must renew and reverify")
    if intent["trust_state"] in {"stale", "contradicted"}:
        return result("REVIEW", "Declaration needs owner re-attestation")
    if intent["intent_type"] in PROTECTED:
        return result("BLOCK", "Resource has a valid protected-purpose declaration")
    if intent["intent_type"] != "disposable_test" or intent["trust_state"] != "verified":
        return result("REVIEW", "Disposable purpose must have a verified telemetry signature")
    checked = intent.get("verified_at")
    if not checked or not timedelta(0) <= now - timestamp(checked) <= timedelta(minutes=10):
        return result(
            "REVIEW", "Verification is missing, from the future, or older than 10 minutes"
        )
    tags = resource.get("tags", {})
    if tags.get("IntentGuardManaged") != "true" or tags.get("IntentGuardDisposable") != "true":
        return result("REVIEW", "Disposable test resource must have both explicit opt-in tags")
    if resource.get("autoscaling") or resource.get("root_device_type") != "ebs":
        return result("BLOCK", "Auto Scaling and instance-store resources are outside this MVP")
    return result("ALLOW", "Verified disposable test resource is eligible for a graceful stop")
