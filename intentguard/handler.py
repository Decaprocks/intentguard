"""Direct IAM-authenticated Lambda invocation; no public HTTP endpoint."""

import logging

from .aws import build_aws_service

logger = logging.getLogger(__name__)


def lambda_handler(event, context):
    try:
        if not isinstance(event, dict):
            raise ValueError("Event must be a JSON object")
        return {"ok": True, "data": build_aws_service().dispatch(event)}
    except (ValueError, KeyError, TypeError) as exc:
        return {"ok": False, "error": str(exc), "error_type": type(exc).__name__}
    except Exception:
        logger.exception("IntentGuard backend operation failed")
        return {
            "ok": False,
            "error": "AWS operation failed; check function logs and lab permissions",
        }
