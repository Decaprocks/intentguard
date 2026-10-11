# Piyush's AWS setup and integration checklist

Dhruv supplies Python code, tests, the dashboard and deployment scripts. Piyush supplies the lab environment, AWS resources, execution role and permission checks. Both verify the deployed application together.

## 1. Get the same code

```sh
git clone https://github.com/Decaprocks/intentguard.git
cd intentguard
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
python -m pytest -q
python -m intentguard demo
```

The repository is private; Dhruv must add teammates as collaborators separately. No collaborators are added by the code.

## 2. Start Learner Lab and set up a local session

Start the lab, wait for readiness and open its AWS Console. Confirm the region used by your lab; examples use `us-east-1`.
Use **AWS Details** to obtain your session credentials. Configure your own AWS profile or export `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_SESSION_TOKEN` and `AWS_DEFAULT_REGION` in your local terminal.
The session token is essential for temporary lab credentials. Refresh credentials when they expire. Do not paste them into code, GitHub, screenshots or chat.

```sh
python scripts/preflight.py --region us-east-1
```

Before deployment, missing table/function results are expected. This read-only check does not prove create or write permission. Record actual access denials so Dhruv can distinguish permission problems from code problems.

## 3. Prepare test resources and role

Use small **EBS-backed standalone EC2 test instances** permitted by the lab. One instance is enough to test scenarios sequentially; two make the protected-versus-disposable demo clearer.
Avoid putting these instances in an Auto Scaling group.

Tags on every project test instance:

| Tag | Value |
|---|---|
| `Name` | `intentguard-standby` or `intentguard-disposable` |
| `IntentGuardManaged` | `true` |
| `IntentGuardDisposable` | `true` only for the disposable test instance |

Find the ARN of an existing Lambda-compatible execution role approved by your lab. Some labs provide a `LabRole`; verify that yours exists, trusts Lambda and has required permissions rather than assuming it.
The deploy script does **not** create or alter IAM roles. `infra/lambda-policy.example.json` is a least-privilege permission example for an account where you may configure a dedicated role; replace its placeholders. A managed lab role may have broader fixed permissions.

## 4. Deploy the supplied backend

This step creates two DynamoDB tables and a Lambda function and may consume lab credits:

```sh
python scripts/deploy.py \
  --region us-east-1 \
  --role-arn arn:aws:iam::YOUR_ACCOUNT_ID:role/YOUR_APPROVED_ROLE
```

Created names:

- `intentguard-intents`: partition key `resource_id`, String, on-demand billing.
- `intentguard-audit`: partition key `event_id`, String, on-demand billing.
- `intentguard`: Python 3.12, handler `intentguard.handler.lambda_handler`, 256 MB, 60-second timeout.

The deployment always sets `ENABLE_EXECUTION=false`, including on redeployment. It performs a discovery smoke check after upload. Empty discovery can be valid if no managed instances exist.
Deployment stops on a permission error; it does not roll back resources already created. Keep track of partial resources and retry after resolving permissions. On an existing function, the script preserves its role and other environment fields.

If scripts cannot create resources but console creation is allowed, create the two tables manually, run `python scripts/package_lambda.py`, upload `dist/intentguard-lambda.zip` to a Python 3.12 Lambda using the approved existing role, and set:

```text
Handler: intentguard.handler.lambda_handler
INTENT_TABLE=intentguard-intents
AUDIT_TABLE=intentguard-audit
ENABLE_EXECUTION=false
```

Keep intent TTL deletion disabled. Expiry is an application policy, and expired records must remain available for owner review.

## 5. Connect the local dashboard

```sh
export AWS_DEFAULT_REGION=us-east-1
export INTENTGUARD_FUNCTION=intentguard
python -m streamlit run app.py --server.address 127.0.0.1
```

Select **AWS Learner Lab**. Discovery should show actual tagged EC2 IDs, not the local demo IDs.
Register declarations in the dashboard. Wait until CloudWatch provides enough 5-minute CPU samples, then click **Refresh verification**. New instances may initially remain unverified.
Use **Evaluate all resources (dry run)** to show decisions and verify the audit history in DynamoDB.

## 6. Optional continuous verification and notifications

```sh
python scripts/schedule_verification.py --region us-east-1
```

This creates a 5-minute EventBridge schedule that invokes `{"operation":"verify_all"}`, plus a source-restricted Lambda invocation permission. It requires additional lab permissions. Manual dashboard refresh remains available if those permissions are blocked.
For SNS, create an approved topic and confirmed subscription in the console, grant the execution role `sns:Publish` on that topic, and set Lambda `SNS_TOPIC_ARN`. The app publishes only on a new stale/contradicted transition. It does not create subscriptions or send messages during local tests.
Owner re-attestation happens through the dashboard renewal form; Step Functions approval orchestration is not implemented in this milestone.

## 7. Optional real stop demonstration

First demonstrate dry runs. For a real demonstration, use only the disposable instance with both opt-in tags, a fresh verified disposable declaration, standalone EBS backing and running state.
The execution role should restrict `ec2:StopInstances` to both required tags. Change Lambda `ENABLE_EXECUTION` to `true`, request an actual stop in the dashboard and type the instance ID to confirm.
Check EC2 reaches stopped state and correlate the decision and `stop_requested` audit events. Restore `ENABLE_EXECUTION=false` afterward. A redeploy resets it automatically.
If AWS returns a timeout, inspect the actual instance state before resubmitting. The stop API and database audit writes are not an atomic transaction.

## What Piyush sends back to Dhruv

Send **non-secret** details: region, function name, table names, test instance IDs, handler setting, exact error messages/codes and successful demo results. Do not send access keys, tokens or passwords.

Acceptance evidence:

1. A declared backup is blocked and remains running.
2. A verified disposable server gets ALLOW in a dry run.
3. An expired declaration gets REVIEW and remains protected from execution.
4. A missing declaration gets REVIEW.
5. Registry and audit records exist in DynamoDB.
6. CloudWatch logs show a working Lambda invocation.
7. Renewal resets verification, then fresh evidence restores eligible trust.

## Common failures

| Symptom | Likely check |
|---|---|
| ExpiredToken | Restart/refresh lab session credentials |
| AccessDenied / UnauthorizedOperation | Existing role and lab restrictions |
| No instances shown | Region and exact `IntentGuardManaged=true` tag |
| Module import error | ZIP must contain `intentguard/` at root; check handler |
| ResourceNotFoundException | Table/function names and deployment region |
| Still unverified | Insufficient, stale or mixed CPU data; wait and refresh |
| Cannot restore contradicted trust | Owner must renew first |

Before ending lab sessions, review active instances and scheduled tasks through the lab console. Keep code and evidence outside the lab so a session ending does not become your only project backup.
