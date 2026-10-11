"""Explicit lab deployment; uses an existing execution role instead of creating IAM roles."""

import argparse
import json

import boto3
from botocore.exceptions import ClientError
from package_lambda import package


def main():
    parser = argparse.ArgumentParser(description="Create two DynamoDB tables and a dry-run Lambda")
    parser.add_argument("--role-arn", required=True, help="Existing role ARN supplied by Piyush")
    parser.add_argument("--region", default="us-east-1")
    parser.add_argument("--prefix", default="intentguard")
    args = parser.parse_args()
    session = boto3.Session(region_name=args.region)
    ddb, functions = session.client("dynamodb"), session.client("lambda")
    for suffix, key in (("intents", "resource_id"), ("audit", "event_id")):
        name = f"{args.prefix}-{suffix}"
        try:
            ddb.describe_table(TableName=name)
        except ddb.exceptions.ResourceNotFoundException:
            ddb.create_table(
                TableName=name,
                KeySchema=[{"AttributeName": key, "KeyType": "HASH"}],
                AttributeDefinitions=[{"AttributeName": key, "AttributeType": "S"}],
                BillingMode="PAY_PER_REQUEST",
            )
        ddb.get_waiter("table_exists").wait(TableName=name)
        # Do NOT use intent expiry as DynamoDB deletion TTL: expired claims must remain REVIEW records.
    code = package().read_bytes()
    try:
        functions.get_function(FunctionName=args.prefix)
    except ClientError as exc:
        if exc.response["Error"]["Code"] != "ResourceNotFoundException":
            raise
        functions.create_function(
            FunctionName=args.prefix,
            Runtime="python3.12",
            Role=args.role_arn,
            Handler="intentguard.handler.lambda_handler",
            Code={"ZipFile": code},
            Timeout=60,
            MemorySize=256,
            Environment={
                "Variables": {
                    "INTENT_TABLE": f"{args.prefix}-intents",
                    "AUDIT_TABLE": f"{args.prefix}-audit",
                    "ENABLE_EXECUTION": "false",
                }
            },
        )
        functions.get_waiter("function_active_v2").wait(FunctionName=args.prefix)
    else:
        # Preserve configured role/environment on redeploy, but force execution back off.
        current = functions.get_function_configuration(FunctionName=args.prefix)
        env = current.get("Environment", {}).get("Variables", {})
        env.update(
            INTENT_TABLE=f"{args.prefix}-intents",
            AUDIT_TABLE=f"{args.prefix}-audit",
            ENABLE_EXECUTION="false",
        )
        functions.update_function_configuration(
            FunctionName=args.prefix,
            Environment={"Variables": env},
            Handler="intentguard.handler.lambda_handler",
            Timeout=60,
        )
        functions.get_waiter("function_updated_v2").wait(FunctionName=args.prefix)
        functions.update_function_code(FunctionName=args.prefix, ZipFile=code)
        functions.get_waiter("function_updated_v2").wait(FunctionName=args.prefix)
    result = functions.invoke(
        FunctionName=args.prefix, Payload=json.dumps({"operation": "discover"}).encode()
    )
    response = json.loads(result["Payload"].read())
    if result.get("FunctionError") or not response.get("ok"):
        raise RuntimeError(f"Deployed, but discovery smoke check failed: {response}")
    print(
        json.dumps(
            {"function": args.prefix, "region": args.region, "smoke_check": response}, indent=2
        )
    )


if __name__ == "__main__":
    main()
