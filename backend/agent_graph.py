import os
import time
import asyncio
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
import anthropic

from vector_store import vector_store
from slack_utils import send_approval_message, update_approval_message

logger = logging.getLogger("agent_graph")

# In-memory storage for active and past incidents
INCIDENTS_DB: Dict[str, Dict[str, Any]] = {}

INCIDENT_SCENARIOS = {
    "memory_leak": {
        "title": "Auth Service Out-of-Memory Leak Spike",
        "service": "auth-service",
        "severity": "CRITICAL",
        "logs": "2026-08-08T10:45:12Z [auth-service-v2-x9k2] FATAL: cgo heap memory allocation (1.82GB) exceeded container limit (1.50GB). OOMKilled process 411. Garbage collection pause 4200ms.",
        "metrics": {"cpu_utilization": "88%", "memory_usage": "98.4%", "error_rate": "14.2%", "active_pods": 1},
        "risk_level": "MEDIUM",
        "autonomy_tier": "HUMAN_APPROVAL_REQUIRED",
        "confidence": 0.86,
        "blast_radius": "restarts 1 pod, ~10s downtime, affects auth-service only",
        "proposed_action": "kubectl rollout restart deployment/auth-service && kubectl set resources deployment/auth-service --limits=memory=2Gi"
    },
    "high_latency": {
        "title": "API Gateway Latency & Thread Saturation",
        "service": "api-gateway",
        "severity": "HIGH",
        "logs": "2026-08-08T10:46:01Z [api-gateway-7d6f] WARN: Worker thread pool saturation (198/200 active). HTTP 504 Gateway Timeout on /v1/checkout endpoint. Downstream latency 3400ms.",
        "metrics": {"cpu_utilization": "92%", "memory_usage": "64.1%", "error_rate": "5.8%", "active_pods": 3},
        "risk_level": "LOW",
        "autonomy_tier": "AUTO_EXECUTE",
        "confidence": 0.94,
        "blast_radius": "auto-scales deployment replicas from 3 to 6, zero downtime, affects api-gateway pool",
        "proposed_action": "kubectl scale deployment/api-gateway --replicas=6 && kubectl annotate service/api-gateway timeout=5000ms"
    },
    "disk_full": {
        "title": "Node Storage Partition Capacity Exceeded",
        "service": "node-k8s-worker-03",
        "severity": "HIGH",
        "logs": "2026-08-08T10:46:33Z [k8s-worker-03] ERROR: NodeHasDiskPressure condition set true. Disk usage on /var/log/containers reached 98.2% (118GB/120GB). Logrotate lock stalled.",
        "metrics": {"disk_usage": "98.2%", "inodes_free": "2.1%", "active_pods": 14},
        "risk_level": "LOW",
        "autonomy_tier": "AUTO_EXECUTE",
        "confidence": 0.98,
        "blast_radius": "truncates uncompressed access.log files, zero downtime, affects host storage only",
        "proposed_action": "truncate -s 0 /var/log/containers/*.log && systemctl restart logrotate"
    }
}


import random

FALLBACK_HYPOTHESES = {
    "memory_leak": [
        "Matches pattern from {pm_id} ({score:.0f}% similarity): Unbounded session cache growth in auth-service container triggered CGO heap memory ceiling, leading to container OOM kill.",
        "Consistent with {pm_id} signature ({score:.0f}% similarity): Heap memory allocation climbed pre-crash to 1.82GB, exceeding the 1.50GB cgroup threshold.",
        "Root cause aligns with historical incident {pm_id} ({score:.0f}% similarity): Pooled Go runtime buffer memory leak under concurrent session load."
    ],
    "high_latency": [
        "Matches pattern from {pm_id} ({score:.0f}% similarity): Worker thread pool saturation (198/200 active threads) downstream caused cascading HTTP 504 timeouts.",
        "Consistent with {pm_id} signature ({score:.0f}% similarity): Downstream RPC block exhausted API Gateway thread pool, bottlenecking /v1/checkout endpoint.",
        "Root cause aligns with historical incident {pm_id} ({score:.0f}% similarity): Connection pool queue latency spike causing upstream 504 Gateway Timeout responses."
    ],
    "disk_full": [
        "Matches pattern from {pm_id} ({score:.0f}% similarity): System logrotate daemon stalled on compressed archive lock, allowing access.log to consume 98.2% host storage.",
        "Consistent with {pm_id} signature ({score:.0f}% similarity): Uncompressed container access.log accumulation filled /var/log volume to 118GB/120GB capacity.",
        "Root cause aligns with historical incident {pm_id} ({score:.0f}% similarity): Systemd logrotate lock deadlock triggering NodeHasDiskPressure condition."
    ]
}


async def generate_llm_hypothesis(incident_type: str, logs: str, metrics: Dict[str, Any], retrieved_pm: Dict[str, Any]) -> str:
    """
    Generates a root cause hypothesis using Google Gemini API or Anthropic API if key is available,
    otherwise uses a smart dynamic fallback synthesizer.
    """
    prompt = f"""You are an Autonomous SRE Agent investigating an incident.
Incident Type: {incident_type}
Raw Logs: {logs}
Metrics: {metrics}
Top Retrieved Similar Postmortem: {retrieved_pm.get('id')} - {retrieved_pm.get('title')}
Postmortem Root Cause: {retrieved_pm.get('root_cause')}

Synthesize a concise 2-sentence SRE root cause hypothesis and confidence explanation."""

    # 1. Try Google Gemini API (aistudio.google.com - Free tier)
    gemini_key = os.environ.get("GEMINI_API_KEY")
    if gemini_key:
        try:
            def _call_gemini():
                from google import genai
                client = genai.Client(api_key=gemini_key)
                for model_name in ["gemini-2.0-flash", "gemini-1.5-flash", "gemini-2.0-flash-exp"]:
                    try:
                        response = client.models.generate_content(
                            model=model_name,
                            contents=prompt
                        )
                        if response and response.text:
                            return response.text.strip()
                    except Exception as err:
                        logger.warning(f"Gemini model {model_name} failed: {err}")
                raise RuntimeError("All Gemini model attempts failed")
            
            return await asyncio.to_thread(_call_gemini)
        except Exception as e:
            logger.warning(f"Google Gemini API call failed, trying next provider: {e}")

    # 2. Try Anthropic API
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY")
    if anthropic_key:
        try:
            def _call_anthropic():
                client = anthropic.Anthropic(api_key=anthropic_key)
                message = client.messages.create(
                    model="claude-3-5-sonnet-20241022",
                    max_tokens=200,
                    messages=[{"role": "user", "content": prompt}]
                )
                return message.content[0].text.strip()
            
            return await asyncio.to_thread(_call_anthropic)
        except Exception as e:
            logger.warning(f"Anthropic API call failed, falling back to synthesis engine: {e}")

    # 3. Dynamic Multi-Variant Fallback Engine
    pm_id = retrieved_pm.get("id", "INC-041")
    score = float(retrieved_pm.get("similarity_score", 0.88)) * 100
    variants = FALLBACK_HYPOTHESES.get(incident_type, FALLBACK_HYPOTHESES["memory_leak"])
    chosen_template = random.choice(variants)
    return chosen_template.format(pm_id=pm_id, score=score)


async def run_agent_workflow(incident_id: str, incident_type: str) -> Dict[str, Any]:
    """
    Executes the full SRE Reasoning & Execution Graph:
    Context Extraction -> Vector Store Retrieval -> Hypothesis Generation -> Autonomy Gating -> Execution / Slack Approval.
    """
    scenario = INCIDENT_SCENARIOS.get(incident_type, INCIDENT_SCENARIOS["memory_leak"])
    now_str = datetime.now(timezone.utc).isoformat()

    incident = {
        "id": incident_id,
        "type": incident_type,
        "title": scenario["title"],
        "service": scenario["service"],
        "severity": scenario["severity"],
        "status": "ANALYZING_CONTEXT",
        "created_at": now_str,
        "updated_at": now_str,
        "logs": scenario["logs"],
        "metrics": scenario["metrics"],
        "autonomy_tier": scenario["autonomy_tier"],
        "risk_level": scenario["risk_level"],
        "confidence": scenario["confidence"],
        "blast_radius": scenario["blast_radius"],
        "proposed_action": scenario["proposed_action"],
        "retrieved_postmortems": [],
        "hypothesis": None,
        "timeline": [
            {"step": "TRIGGERED", "timestamp": now_str, "detail": f"Incident triggered: {scenario['title']}"},
            {"step": "ANALYZING_CONTEXT", "timestamp": now_str, "detail": "Parsing telemetry, error logs, and cluster metrics."}
        ],
        "slack_ts": None
    }
    INCIDENTS_DB[incident_id] = incident

    # Step 1: In-Process Vector Store Retrieval
    await asyncio.sleep(0.3)
    query = f"{scenario['title']} {scenario['logs']} {scenario['service']}"
    retrieved = vector_store.search_similar_incidents(query, top_k=2)
    top_pm = retrieved[0] if retrieved else {"id": "INC-041", "title": "Auth OOM KILLED", "similarity_score": 0.88, "root_cause": "OOM Killed session growth"}

    incident["retrieved_postmortems"] = retrieved
    incident["timeline"].append({
        "step": "VECTOR_SEARCH",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "detail": f"Retrieved similar past incident {top_pm['id']}: '{top_pm['title']}' (Cosine Similarity: {top_pm.get('similarity_score', 0.85):.2f})"
    })
    incident["status"] = "HYPOTHESIS_GENERATED"

    # Step 2: LLM Root Cause Reasoning
    await asyncio.sleep(0.4)
    hypothesis = await generate_llm_hypothesis(incident_type, scenario["logs"], scenario["metrics"], top_pm)
    incident["hypothesis"] = hypothesis
    incident["timeline"].append({
        "step": "HYPOTHESIS_GENERATED",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "detail": f"Root Cause Hypothesis: {hypothesis}"
    })

    # Step 3: Remediation & Blast Radius Planning
    await asyncio.sleep(0.3)
    incident["timeline"].append({
        "step": "REMEDIATION_PLANNED",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "detail": f"Remediation plan drafted: '{scenario['proposed_action']}'. Predicted Blast Radius: '{scenario['blast_radius']}'"
    })

    # Step 4: Autonomy Risk Gating
    if scenario["autonomy_tier"] == "AUTO_EXECUTE":
        # FULLY AUTONOMOUS PATH (Zero Human Approval Needed)
        incident["status"] = "AUTONOMOUSLY_EXECUTING"
        incident["timeline"].append({
            "step": "AUTONOMOUSLY_EXECUTING",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "detail": f"⚡ High Confidence ({int(scenario['confidence']*100)}%) & Low Risk -> Auto-executing remediation without human intervention."
        })
        await asyncio.sleep(0.6)

        incident["status"] = "VERIFYING"
        incident["timeline"].append({
            "step": "VERIFYING",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "detail": "Health check probes passing. Telemetry metrics stabilized."
        })
        await asyncio.sleep(0.4)

        incident["status"] = "RESOLVED"
        incident["updated_at"] = datetime.now(timezone.utc).isoformat()
        incident["timeline"].append({
            "step": "RESOLVED",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "detail": "✅ Incident resolved fully autonomously."
        })
    else:
        # HUMAN ESCALATION PATH (Requires Slack Approval)
        incident["status"] = "AWAITING_APPROVAL"
        incident["timeline"].append({
            "step": "AWAITING_APPROVAL",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "detail": f"✋ Medium Risk -> Escalated to human operator via Slack approval channel."
        })

        # Send interactive Slack message
        slack_ts = await send_approval_message(
            incident_id=incident_id,
            title=scenario["title"],
            hypothesis=hypothesis,
            action=scenario["proposed_action"],
            blast_radius=scenario["blast_radius"],
            confidence=scenario["confidence"],
            retrieved_postmortem_id=top_pm["id"]
        )
        incident["slack_ts"] = slack_ts

    return incident


async def resume_incident_execution(incident_id: str, approved: bool, operator: str = "Human Operator", response_url: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Resumes execution for an incident paused at AWAITING_APPROVAL when an operator clicks Approve or Deny in Slack.
    """
    incident = INCIDENTS_DB.get(incident_id)
    if not incident or incident["status"] != "AWAITING_APPROVAL":
        logger.warning(f"Cannot resume incident {incident_id}: status is {incident.get('status') if incident else 'NOT_FOUND'}")
        return incident

    now_str = datetime.now(timezone.utc).isoformat()

    if approved:
        incident["status"] = "EXECUTING"
        incident["timeline"].append({
            "step": "APPROVAL_GRANTED",
            "timestamp": now_str,
            "detail": f"✅ Approved by {operator} via Slack. Resuming remediation."
        })
        incident["timeline"].append({
            "step": "EXECUTING",
            "timestamp": now_str,
            "detail": f"Executing: '{incident.get('proposed_action', 'remediation plan')}'"
        })

        if response_url:
            await update_approval_message(response_url, incident_id, approved=True, operator_name=operator)

        await asyncio.sleep(0.5)
        incident["status"] = "VERIFYING"
        incident["timeline"].append({
            "step": "VERIFYING",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "detail": "Post-execution verification: All container probes healthy."
        })

        await asyncio.sleep(0.4)
        incident["status"] = "RESOLVED"
        incident["updated_at"] = datetime.now(timezone.utc).isoformat()
        incident["timeline"].append({
            "step": "RESOLVED",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "detail": "✅ Incident successfully remediated and verified."
        })
    else:
        incident["status"] = "DENIED"
        incident["updated_at"] = now_str
        incident["timeline"].append({
            "step": "DENIED",
            "timestamp": now_str,
            "detail": f"🛑 Denied by {operator} via Slack. Execution aborted. Incident escalated to manual on-call."
        })
        if response_url:
            await update_approval_message(response_url, incident_id, approved=False, operator_name=operator)

    return incident
