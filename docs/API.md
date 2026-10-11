# Gateway contract

Invoke `intentguard.handler.lambda_handler` synchronously through the Lambda API.
All callers must be trusted team operators with `lambda:InvokeFunction` on this function.
The direct-invoke response is an application envelope, not an API Gateway HTTP response:

```json
{"ok": true, "data": {"decision": "BLOCK", "reason": "..."}}
```

Errors use `{"ok": false, "error": "..."}`. `LambdaClient` also checks AWS `FunctionError`.
There is no credential, owner authorization or trust-state bypass in the request schema.
Owner identity authorization requires a later authenticated API; currently IAM protects the whole trusted-team function.

## Operations

| Operation | Additional fields | Result |
|---|---|---|
| `discover` | none | EC2 records carrying `IntentGuardManaged=true` |
| `list_intents` | none | Registry records |
| `register` | `intent` object below | Created/renewed unverified declaration |
| `verify` | `resource_id` | Updated trust record |
| `verify_all` | none | Per-resource verification results or errors |
| `optimize` | none | Dry-run stop decisions for discovered resources |
| `request` | `resource_id`, optional `action`, optional boolean `execute` | Audited action decision |
| `history` | none | Latest 200 audit events |

Example declaration (replace instance ID, owner, reason and expiry):

```json
{
  "operation": "register",
  "intent": {
    "resource_id": "i-0123456789abcdef0",
    "owner": "Piyush",
    "intent_type": "warm_standby",
    "reason": "Review demonstration backup",
    "expires_at": "2026-11-01T00:00:00Z",
    "cpu_max_percent": 10
  }
}
```

Allowed types: `warm_standby`, `burst_buffer`, `compliance_replica`, `disposable_test`.
All six intent fields are required; extra fields are rejected. Clients cannot supply `trust_state`, `verified_at` or `version`.
Expiry must be timezone-aware, later than the backend clock and no more than 90 days away.
Renewals preserve the original owner and reset trust to unverified.

Stop request:

```json
{"operation": "request", "resource_id": "i-0123456789abcdef0", "action": "stop", "execute": false}
```

`ALLOW` is permission under this policy, not evidence an action executed. `executed: true` means the EC2 stop request was accepted, not that the instance has already reached stopped state.
`execute: true` requires server-side `ENABLE_EXECUTION=true` as well as every eligibility check. Execution requests are synchronous and have no client idempotency key: after an error, inspect audit and EC2 state before retrying.

## Registry schema

Partition key: `resource_id` (String). Fields: declaration fields, `trust_state`, `verified_at`, `verification_reason`, `version` (Number).
Creates use conditional put; updates require the current version. Reads are strongly consistent.
**Do not enable deletion TTL on `expires_at`.** The gateway evaluates expiry itself. Deleting an expired declaration would erase the re-attestation state and history of protection.

## Verification rule

Fetch 30 minutes of `AWS/EC2` CPUUtilization `Maximum` values at 300-second periods.
Accept finite values in 0–100 only, with unique timestamps not in the future.
Evidence needs at least three samples spanning at least 10 minutes, a newest sample within 10 minutes, and no adjacent gap over 10 minutes.

- Expired: stale.
- Insufficient/old/discontinuous/mixed evidence: unverified.
- All three latest periods above the expected maximum: contradicted.
- All accepted periods at or below it: verified CPU signature.
- Burst buffer: unverified; CPU idleness cannot establish load absorption.
- Stale/contradicted: latched until renewal; quiet telemetry alone cannot restore trust.

## Audit schema

Partition key: `event_id` (String UUID). Each event includes `timestamp`, `kind` and operation-specific fields.
Decision events include resource, action, reason, decision, requested execution and intent version.
An execution produces a separate `stop_requested` event; failures/timeouts produce `execution_failed_or_unknown`.
`registration_requested` and `verification_requested` record attempts, not successful completion.
The local backend retains all events; the UI shows at most 200. AWS history scans the tiny lab table before sorting, so this must be replaced with indexed queries for production scale.
