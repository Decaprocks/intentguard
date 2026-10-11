# Review demonstration

Start with the reproducible **local simulation**, clearly announce simulated data, then show the AWS version only after Piyush has verified it.

## Five-minute local demonstration

1. Run `python -m intentguard demo`. Show BLOCK / ALLOW / REVIEW / REVIEW.
2. Open Streamlit's Resources tab. Explain resource purpose, expiry and trust.
3. Evaluate the standby backup: BLOCK, no execution.
4. Evaluate the disposable server: ALLOW, dry run only.
5. Evaluate the expired backup: REVIEW, no execution.
6. In Declare / renew, renew the expired backup with owner `team-demo`, a future expiry and a reason. Observe unverified trust, then refresh verification and show protection.
7. Download audit JSON and show the decision reasons and renewal events.

The simulated CPU signature is deliberately simple. Explain that CPU matching alone does not prove backup readiness or business necessity.

## AWS demonstration after integration

Follow `PIYUSH_AWS_HANDOFF.md`. Use real instance IDs and display actual DynamoDB records, CloudWatch metrics and Lambda logs. Keep the first demo in dry-run mode. An ALLOW decision does not itself establish measured savings.

## Talk track

"Our system puts a declared purpose between an optimizer and its cloud action. A deliberately idle standby is protected. A disposable test resource can become eligible after verification. Expired or contradicted declarations go back to the owner for renewal rather than automatically losing protection. Each decision has a reason and audit record."

## Evidence to capture

| Scenario | Expected | Evidence |
|---|---|---|
| Protected backup | BLOCK | Declaration, decision and unchanged EC2 state |
| Disposable test | ALLOW dry run | CPU samples, tags, decision and audit |
| Expired declaration | REVIEW | Expiry, stale state and review queue |
| Undeclared resource | REVIEW | Decision reason |
| Contradiction | REVIEW | Sustained threshold violations and latched trust |
| Renewal | Unverified then verified | Updated expiry, new version and fresh telemetry |

Use the automated tests for deterministic contradiction and missing-metric cases. Do not present those mocked results as real CloudWatch measurements.
