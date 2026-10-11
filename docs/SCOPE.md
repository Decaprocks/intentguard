# Proposal coverage and remaining work

The PDF defines the complete project vision. This repository is the first coding milestone and must not be represented as the completed AWS architecture.

| Proposal requirement | This milestone | Remaining work |
|---|---|---|
| Structured intent and expiry | Validation, registry, renewal, explicit expiry checks | Authenticated owner identity and administrative transfers |
| Trust states | verified / unverified / stale / contradicted | Richer evidence and reviewer approvals |
| Telemetry verification | Sustained CPU maximum checks | Workload-specific signatures, burst absorption, heartbeat/failover evidence, statistical drift validation |
| Enforcement gateway | Lambda and local shared service | Mandatory enforcement against direct API bypass |
| Cost optimizer | Built-in dry-run stop planner | Third-party integrations and separately privileged gateway API |
| EC2 | Discovery and gated graceful disposable stop | Rightsizing and broader resource support |
| Auto Scaling | Explicitly excluded from stop eligibility | Safe group-aware optimization |
| DynamoDB | Registry and audit adapters with conditional writes | Indexed audit queries and retention management |
| CloudWatch | CPU retrieval and Lambda logging | Additional metrics/alarms and workload experiments |
| Owner workflow / SNS | Review queue, renewal, optional SNS publishing | Durable Step Functions approvals and authenticated decisions |
| Continuous verification | Optional EventBridge schedule | Batched/large-scale verification and robust notification retries |
| IAM | Example tag-restricted execution policy; authenticated Lambda calls | Optimizer/admin separation and enforced no-bypass roles |
| Config / CloudTrail | Not integrated | Detect and audit bypass actions |
| VPC | Uses standard AWS service endpoints | Public/private subnet architecture and control-plane isolation |
| S3 | Audit JSON can be exported locally | S3 archive, lifecycle and integrity controls |
| Cost Explorer / Budgets / Trusted Advisor | No integration or savings claims | Baseline, alerts, actual optimization measurements |

## Responsibility split

- **Dhruv:** code, Git/GitHub, rule tests, dashboard, fixes and integration support.
- **Piyush:** AWS access, test resources, roles/permissions, deployment, metrics/logs and real-cloud checks.
- **Third teammate:** role not yet confirmed; documentation, architecture diagrams and presentation are useful assignments.

Both Dhruv and Piyush test the deployed behaviour; local unit tests do not replace AWS integration evidence.

## Suggested next milestones

1. Piyush deploys and records real protected/disposable/expired-resource demonstrations.
2. Add distinct owner and optimizer authorization boundaries, workload-specific evidence and authenticated review approval.
3. Implement advanced proposal services only where they support the required behaviour, then measure actual savings and protection outcomes.

Review 2's rubric and deadline have not been supplied. These milestones are implementation suggestions, not confirmed professor requirements.
