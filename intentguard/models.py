"""Validated records shared by the local and AWS backends."""

import math
import re
from datetime import UTC, datetime, timedelta

KINDS = {"warm_standby", "burst_buffer", "compliance_replica", "disposable_test"}
PROTECTED = KINDS - {"disposable_test"}


def utcnow():
    return datetime.now(UTC)


def timestamp(value):
    if not isinstance(value, str):
        raise ValueError("Timestamp must be an ISO 8601 string with a timezone")
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise ValueError("Timestamp must include a timezone")
    return dt.astimezone(UTC)


def iso(dt):
    return dt.astimezone(UTC).isoformat().replace("+00:00", "Z")


def declaration(payload, now):
    allowed = {"resource_id", "owner", "intent_type", "reason", "expires_at", "cpu_max_percent"}
    if not isinstance(payload, dict) or set(payload) != allowed:
        raise ValueError("Declaration must contain exactly: " + ", ".join(sorted(allowed)))
    rid = payload["resource_id"]
    if not isinstance(rid, str) or not re.fullmatch(r"i-[0-9a-f]{8}(?:[0-9a-f]{9})?", rid):
        raise ValueError("Use a valid EC2 instance ID")
    for key in ("owner", "reason"):
        if not isinstance(payload[key], str) or not 1 <= len(payload[key].strip()) <= 500:
            raise ValueError(f"{key} must be nonempty text, at most 500 characters")
    if payload["intent_type"] not in KINDS:
        raise ValueError("Unknown intent type")
    if not now < timestamp(payload["expires_at"]) <= now + timedelta(days=90):
        raise ValueError("Expiry must be in the future and within 90 days")
    threshold = payload["cpu_max_percent"]
    if (
        isinstance(threshold, bool)
        or not isinstance(threshold, (int, float))
        or not math.isfinite(threshold)
        or not 0 <= threshold <= 100
    ):
        raise ValueError("CPU threshold must be a finite number from 0 to 100")
    return {
        **payload,
        "owner": payload["owner"].strip(),
        "reason": payload["reason"].strip(),
        "expires_at": iso(timestamp(payload["expires_at"])),
        "trust_state": "unverified",
        "verified_at": None,
        "verification_reason": "Awaiting telemetry verification",
    }
