import io
import json
from datetime import timedelta
from decimal import Decimal

import boto3
import pytest
from botocore.stub import Stubber

from intentguard.aws import AWSCloud, DynamoStore, LambdaClient, from_ddb, to_ddb
from intentguard.models import declaration
from intentguard.storage import Conflict


def client(service):
    return boto3.client(
        service,
        region_name="us-east-1",
        aws_access_key_id="testing",
        aws_secret_access_key="testing",
    )


def test_cloudwatch_request_and_sorting(now, payload):
    cw = client("cloudwatch")
    with Stubber(cw) as stub:
        stub.add_response(
            "get_metric_statistics",
            {
                "Datapoints": [
                    {"Timestamp": now - timedelta(minutes=5), "Maximum": 2.0, "Unit": "Percent"},
                    {"Timestamp": now - timedelta(minutes=10), "Maximum": 1.0, "Unit": "Percent"},
                ],
                "Label": "CPUUtilization",
            },
            {
                "Namespace": "AWS/EC2",
                "MetricName": "CPUUtilization",
                "Dimensions": [{"Name": "InstanceId", "Value": payload["resource_id"]}],
                "StartTime": now - timedelta(minutes=30),
                "EndTime": now,
                "Period": 300,
                "Statistics": ["Maximum"],
                "Unit": "Percent",
            },
        )
        result = AWSCloud(None, cw).metrics(payload["resource_id"], now)
        assert result[0]["maximum"] == 1.0
        stub.assert_no_pending_responses()


def test_ec2_stop_uses_graceful_api_only(payload):
    ec2 = client("ec2")
    with Stubber(ec2) as stub:
        stub.add_response(
            "stop_instances", {"StoppingInstances": []}, {"InstanceIds": [payload["resource_id"]]}
        )
        AWSCloud(ec2, None).stop(payload["resource_id"])
        stub.assert_no_pending_responses()


def test_missing_ec2_returns_none(payload):
    ec2 = client("ec2")
    with Stubber(ec2) as stub:
        stub.add_client_error(
            "describe_instances",
            service_error_code="InvalidInstanceID.NotFound",
            expected_params={"InstanceIds": [payload["resource_id"]]},
        )
        assert AWSCloud(ec2, None).get(payload["resource_id"]) is None


def test_discovery_paginates_and_filters_managed_resources(payload):
    ec2 = client("ec2")
    instance = {
        "InstanceId": payload["resource_id"],
        "State": {"Name": "running"},
        "RootDeviceType": "ebs",
        "Tags": [{"Key": "IntentGuardManaged", "Value": "true"}],
    }
    filters = [{"Name": "tag:IntentGuardManaged", "Values": ["true"]}]
    with Stubber(ec2) as stub:
        stub.add_response(
            "describe_instances",
            {"Reservations": [{"Instances": [instance]}], "NextToken": "next"},
            {"Filters": filters},
        )
        stub.add_response(
            "describe_instances", {"Reservations": []}, {"Filters": filters, "NextToken": "next"}
        )
        assert len(AWSCloud(ec2, None).discover()) == 1
        stub.assert_no_pending_responses()


def table():
    return boto3.resource(
        "dynamodb",
        region_name="us-east-1",
        aws_access_key_id="testing",
        aws_secret_access_key="testing",
    ).Table("intentguard-intents")


def test_ddb_conditional_create(payload, now):
    registry = table()
    item = declaration(payload, now)
    with Stubber(registry.meta.client) as stub:
        stub.add_response(
            "put_item",
            {},
            {
                "TableName": registry.name,
                "Item": to_ddb({**item, "version": 1}),
                "ConditionExpression": "attribute_not_exists(resource_id)",
            },
        )
        assert DynamoStore(registry, None).save(item)["version"] == 1


def test_ddb_conflict_is_not_overwritten(payload, now):
    registry = table()
    with Stubber(registry.meta.client) as stub:
        stub.add_client_error("put_item", service_error_code="ConditionalCheckFailedException")
        with pytest.raises(Conflict):
            DynamoStore(registry, None).save(declaration(payload, now), 1)


def test_decimal_roundtrip():
    assert to_ddb({"cpu": 2.5}) == {"cpu": Decimal("2.5")}
    assert from_ddb({"cpu": Decimal("2.5")}) == {"cpu": 2.5}
    assert isinstance(from_ddb({"version": Decimal("2")})["version"], int)


def test_lambda_invocation_contract(monkeypatch):
    backend = LambdaClient.__new__(LambdaClient)
    backend.client, backend.function_name = client("lambda"), "intentguard"
    event = {"operation": "discover"}
    with Stubber(backend.client) as stub:
        stub.add_response(
            "invoke",
            {
                "StatusCode": 200,
                "Payload": io.BytesIO(json.dumps({"ok": True, "data": []}).encode()),
            },
            {
                "FunctionName": "intentguard",
                "InvocationType": "RequestResponse",
                "Payload": json.dumps(event).encode(),
            },
        )
        assert backend.dispatch(event) == []


def test_handler_validation_error(monkeypatch):
    from intentguard import handler

    monkeypatch.setattr(handler, "build_aws_service", lambda: None)
    assert handler.lambda_handler([], None)["ok"] is False


def test_handler_dispatch(service, monkeypatch):
    from intentguard import handler

    monkeypatch.setattr(handler, "build_aws_service", lambda: service)
    assert len(handler.lambda_handler({"operation": "discover"}, None)["data"]) == 4
