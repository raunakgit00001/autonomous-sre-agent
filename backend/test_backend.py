import asyncio
import time
import hmac
import hashlib
import os
import urllib.parse
from fastapi.testclient import TestClient

from main import app
from vector_store import vector_store
from slack_utils import verify_signature
from agent_graph import run_agent_workflow, resume_incident_execution, INCIDENTS_DB

client = TestClient(app)

async def test_vector_store():
    print("Testing Vector Store Retrieval...")
    query = "Auth Service Out-of-Memory Leak Spike cgo heap memory allocation (1.82GB) exceeded container limit auth-service"
    results = vector_store.search_similar_incidents(query, top_k=2)
    assert len(results) >= 1, "Vector search returned empty list"
    top_match = results[0]
    print(f"  Top Match ID: {top_match['id']}, Title: '{top_match['title']}', Score: {top_match.get('similarity_score')}")
    assert top_match['id'] == "INC-041", f"Expected INC-041, got {top_match['id']}"
    print("[OK] Vector Store Test Passed!")

def test_slack_signature_unit():
    print("Testing Slack Signature Verification Function (Raw Body)...")
    secret = "8f7a6b5c4d3e2f1a"
    raw_body = b"payload=%7B%22type%22%3A%22block_actions%22%7D"
    now_ts = str(int(time.time()))
    
    sig_basestring = f"v0:{now_ts}:".encode('utf-8') + raw_body
    valid_sig = 'v0=' + hmac.new(secret.encode('utf-8'), sig_basestring, hashlib.sha256).hexdigest()
    
    assert verify_signature(raw_body, now_ts, valid_sig, secret) is True, "Valid signature failed verification"
    assert verify_signature(raw_body, now_ts, "v0=invalid", secret) is False, "Invalid signature passed verification"
    print("[OK] Slack Signature Unit Test Passed!")

def test_fastapi_slack_route_integration():
    print("Testing FastAPI Slack Interactive Webhook Route (HTTP Pipeline + Signature Verification)...")
    secret = "my_slack_secret_12345"
    os.environ["SLACK_SIGNING_SECRET"] = secret

    # Seed an incident paused at AWAITING_APPROVAL
    incident_id = "INC-HTTP-TEST-01"
    INCIDENTS_DB[incident_id] = {
        "id": incident_id,
        "type": "memory_leak",
        "title": "Test Memory Leak",
        "status": "AWAITING_APPROVAL",
        "autonomy_tier": "HUMAN_APPROVAL_REQUIRED",
        "proposed_action": "kubectl rollout restart deployment/auth-service",
        "timeline": []
    }

    payload_json = {
        "user": {"name": "Test Operator"},
        "actions": [{"value": f"{incident_id}:approve"}],
        "response_url": "https://hooks.slack.com/actions/test"
    }

    # Encode raw body as Slack sends it
    raw_body_str = urllib.parse.urlencode({"payload": str(payload_json).replace("'", '"')}).encode('utf-8')
    now_ts = str(int(time.time()))

    sig_basestring = f"v0:{now_ts}:".encode('utf-8') + raw_body_str
    valid_sig = 'v0=' + hmac.new(secret.encode('utf-8'), sig_basestring, hashlib.sha256).hexdigest()

    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "X-Slack-Signature": valid_sig,
        "X-Slack-Request-Timestamp": now_ts
    }

    # Send POST request through FastAPI HTTP pipeline
    response = client.post("/api/slack/interactive", content=raw_body_str, headers=headers)
    assert response.status_code == 200, f"Expected 200 OK, got {response.status_code}: {response.text}"
    assert response.json() == {"ok": True}
    print("[OK] FastAPI Slack Interactive Route Test Passed!")

async def test_autonomous_workflow():
    print("Testing Autonomous Workflow (high_latency)...")
    incident_id = "TEST-AUTO-01"
    incident = await run_agent_workflow(incident_id, "high_latency")
    
    assert incident["status"] == "RESOLVED", f"Expected RESOLVED, got {incident['status']}"
    assert incident["autonomy_tier"] == "AUTO_EXECUTE", f"Expected AUTO_EXECUTE, got {incident['autonomy_tier']}"
    print("  Status:", incident["status"], "| Autonomy Tier:", incident["autonomy_tier"])
    print("[OK] Autonomous Workflow Test Passed!")

async def test_human_approval_workflow():
    print("Testing Human Approval Workflow (memory_leak)...")
    incident_id = "TEST-HUMAN-01"
    incident = await run_agent_workflow(incident_id, "memory_leak")
    
    assert incident["status"] == "AWAITING_APPROVAL", f"Expected AWAITING_APPROVAL, got {incident['status']}"
    assert incident["autonomy_tier"] == "HUMAN_APPROVAL_REQUIRED", f"Expected HUMAN_APPROVAL_REQUIRED, got {incident['autonomy_tier']}"
    print("  Paused Status:", incident["status"], "| Autonomy Tier:", incident["autonomy_tier"])
    
    # Simulate Approval Resume
    resumed = await resume_incident_execution(incident_id, approved=True, operator="Test User")
    assert resumed["status"] == "RESOLVED", f"Expected RESOLVED after approval, got {resumed['status']}"
    print("  Resumed Status:", resumed["status"])
    print("[OK] Human Approval Workflow Test Passed!")

async def main():
    await test_vector_store()
    test_slack_signature_unit()
    test_fastapi_slack_route_integration()
    await test_autonomous_workflow()
    await test_human_approval_workflow()
    print("\nALL BACKEND TESTS PASSED SUCCESSFULLY!")

if __name__ == "__main__":
    asyncio.run(main())
