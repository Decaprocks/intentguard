"""Simple sustained CPU-signature check; does not prove business purpose."""

import math
from datetime import timedelta
from itertools import pairwise

from .models import iso, timestamp


def verify(intent, points, now):
    if timestamp(intent["expires_at"]) <= now:
        state, reason = "stale", "Expired declaration; owner renewal required"
    elif intent["intent_type"] == "burst_buffer":
        state, reason = (
            "unverified",
            "Burst absorption requires workload-specific evidence beyond this CPU check",
        )
    else:
        samples = {}
        for point in points:
            dt = timestamp(point["timestamp"])
            value = point["maximum"]
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                or not 0 <= value <= 100
            ):
                continue
            if now - timedelta(minutes=30) <= dt <= now:
                samples[dt] = value
        dates = sorted(samples)
        enough = (
            len(dates) >= 3
            and dates[-1] >= now - timedelta(minutes=10)
            and dates[-1] - dates[0] >= timedelta(minutes=10)
            and all(b - a <= timedelta(minutes=10) for a, b in pairwise(dates))
        )
        if not enough:
            state, reason = "unverified", "Insufficient, stale or discontinuous CPU evidence"
        elif all(samples[d] > intent["cpu_max_percent"] for d in dates[-3:]):
            state, reason = (
                "contradicted",
                "CPU exceeded declared threshold for three consecutive periods",
            )
        elif any(samples[d] > intent["cpu_max_percent"] for d in dates):
            state, reason = "unverified", "Mixed CPU evidence; further observation required"
        else:
            state, reason = (
                "verified",
                "Observed CPU signature matches; business purpose is owner-declared",
            )
    # Contradictions are latched until owner renewal, even if metrics later quiet down.
    if intent["trust_state"] in {"stale", "contradicted"} and state != "stale":
        state, reason = (
            intent["trust_state"],
            "Owner renewal required before verification can restore trust",
        )
    return {
        **intent,
        "trust_state": state,
        "verified_at": iso(now) if state == "verified" else None,
        "verification_reason": reason,
    }
