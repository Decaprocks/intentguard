"""Read-only checks; does not launch instances or create AWS resources."""

import argparse
import json

import boto3
from botocore.exceptions import ClientError

parser = argparse.ArgumentParser()
parser.add_argument("--region", default="us-east-1")
parser.add_argument("--prefix", default="intentguard")
args = parser.parse_args()
session = boto3.Session(region_name=args.region)


def check(label, action):
    try:
        action()
        return {"check": label, "status": "OK"}
    except ClientError as exc:
        return {"check": label, "status": exc.response["Error"]["Code"]}
    except Exception as exc:
        return {"check": label, "status": type(exc).__name__}


checks = [
    check("Session identity", lambda: session.client("sts").get_caller_identity()),
    check("EC2 discovery", lambda: session.client("ec2").describe_instances(MaxResults=5)),
    check(
        "CloudWatch visibility",
        lambda: session.client("cloudwatch").list_metrics(Namespace="AWS/EC2"),
    ),
    check(
        "Intent table",
        lambda: session.client("dynamodb").describe_table(TableName=f"{args.prefix}-intents"),
    ),
    check(
        "Audit table",
        lambda: session.client("dynamodb").describe_table(TableName=f"{args.prefix}-audit"),
    ),
    check(
        "Lambda visibility", lambda: session.client("lambda").get_function(FunctionName=args.prefix)
    ),
]
print(json.dumps(checks, indent=2))
print("Read-only checks do not establish create/write/stop permissions.")
