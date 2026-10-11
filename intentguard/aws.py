"""AWS adapters. Credentials come from the standard Boto3 credential chain."""

import json
import os
from datetime import timedelta
from decimal import Decimal

from .models import iso
from .storage import Conflict


def to_ddb(value):
    return json.loads(json.dumps(value), parse_float=Decimal)


def from_ddb(value):
    def convert(v):
        if isinstance(v, Decimal):
            return int(v) if v == v.to_integral_value() else float(v)
        raise TypeError(f"Unsupported DynamoDB value: {type(v).__name__}")

    return json.loads(json.dumps(value, default=convert))


class DynamoStore:
    def __init__(self, registry, audit_table):
        self.registry, self.audit_table = registry, audit_table

    def get(self, rid):
        item = self.registry.get_item(Key={"resource_id": rid}, ConsistentRead=True).get("Item")
        return from_ddb(item) if item else None

    def save(self, item, expected_version=0):
        from botocore.exceptions import ClientError

        item = {**item, "version": expected_version + 1}
        options = {"Item": to_ddb(item)}
        if expected_version == 0:
            options["ConditionExpression"] = "attribute_not_exists(resource_id)"
        else:
            options.update(
                ConditionExpression="#v = :v",
                ExpressionAttributeNames={"#v": "version"},
                ExpressionAttributeValues={":v": expected_version},
            )
        try:
            self.registry.put_item(**options)
        except ClientError as exc:
            if exc.response["Error"]["Code"] == "ConditionalCheckFailedException":
                raise Conflict("Record changed; refresh and retry") from exc
            raise
        return item

    @staticmethod
    def scan(table):
        items, options = [], {"ConsistentRead": True}
        while True:
            page = table.scan(**options)
            items.extend(page.get("Items", []))
            if "LastEvaluatedKey" not in page:
                return from_ddb(items)
            options["ExclusiveStartKey"] = page["LastEvaluatedKey"]

    def list(self):
        return sorted(self.scan(self.registry), key=lambda i: i["resource_id"])

    def audit(self, event):
        self.audit_table.put_item(
            Item=to_ddb(event), ConditionExpression="attribute_not_exists(event_id)"
        )

    def history(self):
        # Full scan is acceptable for a tiny lab; add time-indexed queries before scaling.
        return sorted(self.scan(self.audit_table), key=lambda i: i["timestamp"], reverse=True)[:200]


class AWSCloud:
    def __init__(self, ec2, cloudwatch):
        self.ec2, self.cloudwatch = ec2, cloudwatch

    @staticmethod
    def normalize(item):
        tags = {t["Key"]: t["Value"] for t in item.get("Tags", [])}
        return {
            "resource_id": item["InstanceId"],
            "name": tags.get("Name", item["InstanceId"]),
            "state": item["State"]["Name"],
            "root_device_type": item.get("RootDeviceType"),
            "autoscaling": "aws:autoscaling:groupName" in tags,
            "tags": tags,
        }

    def discover(self):
        resources = []
        for page in self.ec2.get_paginator("describe_instances").paginate(
            Filters=[{"Name": "tag:IntentGuardManaged", "Values": ["true"]}]
        ):
            for reservation in page["Reservations"]:
                resources.extend(self.normalize(i) for i in reservation["Instances"])
        return resources

    def get(self, rid):
        from botocore.exceptions import ClientError

        try:
            page = self.ec2.describe_instances(InstanceIds=[rid])
        except ClientError as exc:
            if exc.response["Error"]["Code"] == "InvalidInstanceID.NotFound":
                return None
            raise
        items = [i for r in page["Reservations"] for i in r["Instances"]]
        return self.normalize(items[0]) if items else None

    def metrics(self, rid, now):
        page = self.cloudwatch.get_metric_statistics(
            Namespace="AWS/EC2",
            MetricName="CPUUtilization",
            Dimensions=[{"Name": "InstanceId", "Value": rid}],
            StartTime=now - timedelta(minutes=30),
            EndTime=now,
            Period=300,
            Statistics=["Maximum"],
            Unit="Percent",
        )
        return [
            {"timestamp": iso(p["Timestamp"]), "maximum": p["Maximum"]}
            for p in sorted(page.get("Datapoints", []), key=lambda p: p["Timestamp"])
        ]

    def stop(self, rid):
        # Default graceful shutdown only; no termination, force or hibernation.
        return self.ec2.stop_instances(InstanceIds=[rid])


def build_aws_service():
    import boto3

    from .service import Service

    session = boto3.Session()
    ddb = session.resource("dynamodb")
    topic = os.environ.get("SNS_TOPIC_ARN")

    def notify(item):
        session.client("sns").publish(
            TopicArn=topic,
            Subject="IntentGuard: owner review needed",
            Message=json.dumps(
                {
                    "resource_id": item["resource_id"],
                    "owner": item["owner"],
                    "trust_state": item["trust_state"],
                    "reason": item["verification_reason"],
                }
            ),
        )

    return Service(
        DynamoStore(ddb.Table(os.environ["INTENT_TABLE"]), ddb.Table(os.environ["AUDIT_TABLE"])),
        AWSCloud(session.client("ec2"), session.client("cloudwatch")),
        execution_enabled=os.environ.get("ENABLE_EXECUTION", "false").lower() == "true",
        notifier=notify if topic else None,
    )


class LambdaClient:
    def __init__(self, function_name):
        import boto3

        self.client = boto3.client("lambda")
        self.function_name = function_name

    def dispatch(self, event):
        result = self.client.invoke(
            FunctionName=self.function_name,
            InvocationType="RequestResponse",
            Payload=json.dumps(event).encode(),
        )
        body = json.loads(result["Payload"].read())
        if result.get("FunctionError"):
            raise RuntimeError("Lambda failed; Piyush should inspect CloudWatch logs")
        if not body.get("ok"):
            raise ValueError(body.get("error", "Backend request failed"))
        return body["data"]
