"""Streamlit dashboard with local simulation and authenticated AWS modes."""

import json
import os
from datetime import timedelta

import streamlit as st

from intentguard.aws import LambdaClient
from intentguard.demo import DemoCloud, seed
from intentguard.models import iso, utcnow
from intentguard.service import Service
from intentguard.storage import SQLiteStore

st.set_page_config(page_title="IntentGuard", page_icon="🛡️", layout="wide")
st.title("🛡️ IntentGuard")
st.caption("Protect resources by their purpose. Review uncertainty before optimizing.")
mode = st.sidebar.radio("Environment", ["Local demo", "AWS Learner Lab"])
if st.session_state.get("result_environment") != mode:
    st.session_state.pop("last_decision", None)
    st.session_state.pop("last_plan", None)
    st.session_state["result_environment"] = mode


@st.cache_resource
def local_backend():
    service = Service(SQLiteStore(), DemoCloud())
    seed(service)
    return service


if mode == "Local demo":
    backend = local_backend()
    st.info("Simulated resources and CPU data • decisions are dry runs • no AWS credentials needed")
else:
    function_name = st.sidebar.text_input(
        "Lambda function", os.getenv("INTENTGUARD_FUNCTION", "intentguard")
    )
    st.sidebar.caption(
        "AWS credentials are read from your local AWS profile or exported session variables."
    )
    try:
        backend = LambdaClient(function_name)
    except Exception as exc:
        st.error(f"AWS connection unavailable: {type(exc).__name__}. Check the handoff guide.")
        st.stop()
    st.info("AWS resources • IAM-authenticated Lambda • dry run unless explicitly requested")


def call(event):
    try:
        return backend.dispatch(event)
    except Exception as exc:
        st.error(f"Request failed: {exc}")
        return None


if st.button("Refresh verification"):
    result = call({"operation": "verify_all"})
    if result is not None:
        errors = [i for i in result if "error" in i]
        if errors:
            st.warning(
                f"{len(errors)} resources could not be verified. Check AWS access and retry."
            )
        else:
            st.success("Verification updated")

resources = call({"operation": "discover"})
intents = call({"operation": "list_intents"})
if resources is None or intents is None:
    st.stop()
by_id = {i["resource_id"]: i for i in intents}
cols = st.columns(3)
cols[0].metric("Managed resources", len(resources))
cols[1].metric("Declarations", len(intents))
cols[2].metric(
    "Awaiting owner review", sum(i["trust_state"] in {"stale", "contradicted"} for i in intents)
)
overview, declare, optimize, audit = st.tabs(
    ["Resources", "Declare / renew", "Optimization", "Audit history"],
    key="workspace",
    on_change="rerun",
)

with overview:
    rows = [
        {
            "Resource": r["name"],
            "ID": r["resource_id"],
            "State": r["state"],
            "Purpose": by_id.get(r["resource_id"], {}).get("intent_type", "undeclared"),
            "Trust": by_id.get(r["resource_id"], {}).get("trust_state", "unregistered"),
            "Expires": by_id.get(r["resource_id"], {}).get("expires_at", "—"),
        }
        for r in resources
    ]
    st.dataframe(rows, width="stretch", hide_index=True)
    st.caption(
        "Verified means the observed CPU signature matches. It does not prove backup readiness or compliance."
    )
    for i in intents:
        if i["trust_state"] in {"stale", "contradicted"}:
            st.warning(
                f"{i['resource_id']} • {i['owner']}: {i['verification_reason']}. Renew under Declare / renew."
            )

options = {r["resource_id"]: f"{r['name']} ({r['resource_id']})" for r in resources}
with declare:
    if options:
        with st.form("declaration"):
            rid = st.selectbox("Resource", list(options), format_func=options.get)
            owner = st.text_input("Owner", "Dhruv")
            kind = st.selectbox(
                "Purpose", ["warm_standby", "burst_buffer", "compliance_replica", "disposable_test"]
            )
            reason = st.text_area("Why does this resource exist?")
            days = st.number_input("Valid for days", 1, 90, 7)
            threshold = st.number_input("Expected maximum CPU (%)", 0.0, 100.0, 10.0)
            submit = st.form_submit_button("Save declaration")
        if submit:
            saved = call(
                {
                    "operation": "register",
                    "intent": {
                        "resource_id": rid,
                        "owner": owner,
                        "intent_type": kind,
                        "reason": reason,
                        "expires_at": iso(utcnow() + timedelta(days=days)),
                        "cpu_max_percent": threshold,
                    },
                }
            )
            if saved:
                st.success(
                    "Saved as unverified. Refresh verification to check the telemetry signature."
                )
    else:
        st.write(
            "No managed resources. Piyush should tag the test EC2 instance IntentGuardManaged=true."
        )

with optimize:
    if st.button("Evaluate all resources (dry run)"):
        plan = call({"operation": "optimize"})
        if plan is not None:
            st.session_state["last_plan"] = plan
    if st.session_state.get("last_plan"):
        st.dataframe(st.session_state["last_plan"], width="stretch", hide_index=True)
    if options:
        rid = st.selectbox("Resource to evaluate", list(options), format_func=options.get)
        execute = False
        if mode != "Local demo":
            execute = st.checkbox("Request an actual stop on this disposable test instance")
            if execute:
                confirmation = st.text_input("Type the instance ID to confirm")
            else:
                confirmation = ""
        else:
            confirmation = ""
        if st.button("Evaluate stop request", disabled=execute and confirmation != rid):
            decision = call(
                {"operation": "request", "resource_id": rid, "action": "stop", "execute": execute}
            )
            if decision:
                st.session_state["last_decision"] = decision
        if st.session_state.get("last_decision"):
            decision = st.session_state["last_decision"]
            show = {"ALLOW": st.success, "BLOCK": st.error, "REVIEW": st.warning}[
                decision["decision"]
            ]
            show(f"{decision['decision']}: {decision['reason']}")
            st.write(
                "Stop requested on AWS" if decision["executed"] else "No resource change executed"
            )
            st.caption(
                "Last evaluated request; run a fresh request after changing the resource or declaration."
            )
            st.json(decision)

with audit:
    history = call({"operation": "history"})
    if history is not None:
        st.dataframe(history, width="stretch", hide_index=True)
        st.download_button(
            "Download audit JSON",
            json.dumps(history, indent=2),
            "intentguard-audit.json",
            "application/json",
        )
