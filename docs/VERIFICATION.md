# Verification evidence

Local verification performed on 11 October 2026.

## Confirmed

- Automated tests cover policy decisions, expiry, renewal, stale/contradicted latching, missing/stale/future/discontinuous telemetry, resource opt-in tags, execution gating, registry conflict handling, failed audit writes, concurrent renewal and notification transitions.
- Botocore Stubber verifies EC2 discovery pagination, graceful stop arguments, CloudWatch request parameters, DynamoDB conditional writes and Lambda invocation envelopes.
- Streamlit AppTest runs the actual dashboard and submits a disposable-resource dry-run request, producing ALLOW with `executed=false`.
- Browser checks on the running local application confirmed the simulated-resource banner, successful verification refresh, BLOCK for the standby and ALLOW for the disposable server, both with no resource change executed. The Optimization tab remains selected after evaluation.
- The command-line demo produces BLOCK / ALLOW / REVIEW / REVIEW.
- Lambda ZIP packaging and Python compilation succeed.
- Lint and formatting checks are included in GitHub Actions.

Local runtime: Python 3.14; Boto3 1.43.111; Streamlit 1.65.0; pytest 9.1.1; Ruff 0.17.0.
CI separately checks Python 3.11 and 3.12. Consult the repository's Actions page for current results.

## Not established by these checks

No AWS account resources were provisioned or stopped during local development. Real Learner Lab permissions, DynamoDB writes, Lambda execution, CloudWatch metrics, SNS delivery and scheduled invocation require Piyush's integration checks.

CPU signature matching is a limited prototype verifier. Neither these tests nor a green CI run prove business necessity, failover readiness, measured savings, or enforcement against API calls that bypass the gateway.

## Reference documentation checked

- [EC2 StopInstances](https://docs.aws.amazon.com/boto3/latest/reference/services/ec2/client/stop_instances.html): graceful stop and API request arguments.
- [CloudWatch GetMetricStatistics](https://docs.aws.amazon.com/boto3/latest/reference/services/cloudwatch/client/get_metric_statistics.html): metric periods and statistics.
- [DynamoDB PutItem](https://docs.aws.amazon.com/boto3/latest/reference/services/dynamodb/client/put_item.html): conditional writes.
- [DynamoDB TTL](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/TTL.html): deletion TTL is separate from IntentGuard's immediate policy expiry checks.
- [Lambda Invoke](https://docs.aws.amazon.com/boto3/latest/reference/services/lambda/client/invoke.html): synchronous payload response and function-error handling.
- [Streamlit tabs](https://docs.streamlit.io/develop/api-reference/layout/st.tabs): stateful tab navigation.
