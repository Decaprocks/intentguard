# Permissions

`lambda-policy.example.json` describes permissions for a dedicated Lambda execution role.
Replace `REGION` and `ACCOUNT_ID`; it is not a ready-to-attach policy until customized.
The role must trust `lambda.amazonaws.com` to assume it.
For the initial dry-run demo, omit the stop statement entirely if preferred.
Optional SNS requires an additional `sns:Publish` permission scoped to your topic ARN.

The local dashboard operator requires only `lambda:InvokeFunction` on the IntentGuard function.
The deployment operator separately needs permission for the script's DynamoDB create/describe operations,
Lambda create/read/update/invoke operations and `iam:PassRole` on the approved execution role.
Optional scheduling additionally needs EventBridge put-rule/put-targets and Lambda add-permission/get-policy.

Managed Learner Lab roles may not allow custom policies. Validate your actual environment.
This example has no effect until attached and is not proof that bypass is prevented.
Do not give a future untrusted optimizer permission to invoke this combined administrative function;
split the declaration and optimization APIs with different roles first.
