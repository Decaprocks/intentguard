"""Optional EventBridge verification schedule for the small lab deployment."""

import argparse
import json

import boto3
from botocore.exceptions import ClientError

parser = argparse.ArgumentParser()
parser.add_argument("--region", default="us-east-1")
parser.add_argument("--function", default="intentguard")
args = parser.parse_args()
session = boto3.Session(region_name=args.region)
events, functions = session.client("events"), session.client("lambda")
function_arn = functions.get_function(FunctionName=args.function)["Configuration"]["FunctionArn"]
rule_name = f"{args.function}-verify"
rule_arn = events.put_rule(
    Name=rule_name,
    ScheduleExpression="rate(5 minutes)",
    State="ENABLED",
    Description="Verify IntentGuard declarations; never execute optimization",
)["RuleArn"]
statement_id = "intentguard-scheduled-verification"
try:
    functions.add_permission(
        FunctionName=args.function,
        StatementId=statement_id,
        Action="lambda:InvokeFunction",
        Principal="events.amazonaws.com",
        SourceArn=rule_arn,
    )
except ClientError as exc:
    if exc.response["Error"]["Code"] != "ResourceConflictException":
        raise
    policy = json.loads(functions.get_policy(FunctionName=args.function)["Policy"])
    existing = next((s for s in policy["Statement"] if s["Sid"] == statement_id), None)
    if (
        not existing
        or existing.get("Condition", {}).get("ArnLike", {}).get("AWS:SourceArn") != rule_arn
    ):
        raise RuntimeError(
            "Existing schedule permission has a different source; inspect it before retrying"
        ) from exc
result = events.put_targets(
    Rule=rule_name,
    Targets=[
        {"Id": "verify", "Arn": function_arn, "Input": json.dumps({"operation": "verify_all"})}
    ],
)
if result["FailedEntryCount"]:
    raise RuntimeError(f"Schedule target setup failed: {result['FailedEntries']}")
print(
    json.dumps(
        {"rule": rule_name, "schedule": "every 5 minutes", "execution": "verification only"},
        indent=2,
    )
)
