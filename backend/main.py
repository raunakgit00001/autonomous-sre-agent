import os
import json
import uuid
import asyncio
import urllib.parse
import logging
from typing import Optional
from fastapi import FastAPI, Request, HTTPException, BackgroundTasks, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from agent_graph import run_agent_workflow, resume_incident_execution, INCIDENTS_DB
from slack_utils import verify_signature

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("main")

app = FastAPI(
    title="Autonomous SRE Agent API",
    version="1.0.0",
    description="Backend API for Autonomous SRE Incident Reasoning, In-Process Vector Search, Autonomy Gating & Slack Approval Loop"
)

# Enable CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class TriggerIncidentRequest(BaseModel):
    type: str = Field(..., description="Incident type: 'memory_leak', 'high_latency', or 'disk_full'")


class LocalApprovalRequest(BaseModel):
    approved: bool = True
    operator: Optional[str] = "Dashboard Operator"


@app.get("/")
def health_check():
    return {
        "status": "online",
        "system": "Autonomous SRE Agent API",
        "incidents_active": len(INCIDENTS_DB)
    }


@app.post("/api/incidents/trigger")
async def trigger_incident(req: TriggerIncidentRequest, background_tasks: BackgroundTasks):
    valid_types = ["memory_leak", "high_latency", "disk_full"]
    if req.type not in valid_types:
        raise HTTPException(status_code=400, detail=f"Invalid incident type. Must be one of: {valid_types}")

    incident_id = f"INC-{uuid.uuid4().hex[:6].upper()}"
    
    # Start agent workflow in background task
    background_tasks.add_task(run_agent_workflow, incident_id, req.type)

    return {
        "ok": True,
        "incident_id": incident_id,
        "message": f"Triggered incident simulation: {req.type}"
    }


@app.get("/api/incidents")
def list_incidents():
    incidents = list(INCIDENTS_DB.values())
    incidents.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return {"incidents": incidents}


@app.get("/api/incidents/{incident_id}")
def get_incident(incident_id: str):
    incident = INCIDENTS_DB.get(incident_id)
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")
    return incident


@app.post("/api/incidents/{incident_id}/approve")
async def approve_incident_local(incident_id: str, req: LocalApprovalRequest = LocalApprovalRequest()):
    """Local simulation endpoint for approving an incident directly from dashboard/tests."""
    updated = await resume_incident_execution(
        incident_id=incident_id,
        approved=req.approved,
        operator=req.operator or "Dashboard User"
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Incident not found or not in AWAITING_APPROVAL state")
    return {"ok": True, "incident": updated}


@app.post("/api/slack/interactive")
async def slack_interactive_webhook(request: Request):
    """
    Slack interactive components webhook endpoint (handles Approve / Deny button clicks).
    CRITICAL: Reads raw bytes via await request.body() BEFORE any parsing to compute HMAC signature.
    """
    # 1. READ RAW REQUEST BODY FIRST (Essential for HMAC-SHA256 verification)
    raw_body = await request.body()
    
    headers = request.headers
    signature = headers.get("X-Slack-Signature", "")
    timestamp = headers.get("X-Slack-Request-Timestamp", "")
    signing_secret = os.environ.get("SLACK_SIGNING_SECRET", "")

    # 2. VERIFY SLACK SIGNATURE IF SECRET IS CONFIGURED
    if signing_secret:
        is_valid = verify_signature(raw_body, timestamp, signature, signing_secret)
        if not is_valid:
            logger.warning("Rejecting Slack webhook request: invalid signature.")
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Slack signature")
    else:
        logger.info("SLACK_SIGNING_SECRET not set; bypassing signature check in development mode.")

    # 3. PARSE URL-ENCODED FORM PAYLOAD
    body_str = raw_body.decode("utf-8")
    parsed_form = urllib.parse.parse_qs(body_str)
    
    payload_raw = parsed_form.get("payload", ["{}"])[0]
    try:
        payload = json.loads(payload_raw)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON in payload parameter")

    # Extract user and action details
    user_info = payload.get("user", {})
    user_name = user_info.get("username") or user_info.get("name") or "Slack Operator"
    response_url = payload.get("response_url")
    
    actions = payload.get("actions", [])
    if not actions:
        return {"ok": True}

    action_val = actions[0].get("value", "")
    if ":" not in action_val:
        logger.warning(f"Unrecognized Slack action value: {action_val}")
        return {"ok": True}

    incident_id, decision = action_val.split(":", 1)
    approved = (decision == "approve")

    logger.info(f"Received Slack button click for incident {incident_id}: decision={decision}, user={user_name}")

    # Resume execution in background task
    asyncio.create_task(
        resume_incident_execution(
            incident_id=incident_id,
            approved=approved,
            operator=user_name,
            response_url=response_url
        )
    )

    return {"ok": True}
