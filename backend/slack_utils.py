import hmac
import hashlib
import time
import os
import logging
from typing import Dict, Any, Optional
import httpx

logger = logging.getLogger("slack_utils")

def verify_signature(raw_body: bytes, timestamp: str, signature: str, signing_secret: str) -> bool:
    """
    Validates the X-Slack-Signature header against the raw HTTP request body bytes using HMAC-SHA256.
    Prevent replay attacks by rejecting timestamps older than 5 minutes.
    """
    if not signing_secret or not signature or not timestamp:
        logger.warning("Missing Slack signature, timestamp, or signing secret.")
        return False

    try:
        req_timestamp = int(timestamp)
        now = int(time.time())
        if abs(now - req_timestamp) > 60 * 5:
            logger.warning("Slack request timestamp is expired (> 300 seconds).")
            return False
    except ValueError:
        logger.warning("Invalid timestamp format.")
        return False

    sig_basestring = f"v0:{timestamp}:".encode('utf-8') + raw_body
    my_signature = 'v0=' + hmac.new(
        signing_secret.encode('utf-8'),
        sig_basestring,
        hashlib.sha256
    ).hexdigest()

    return hmac.compare_digest(my_signature, signature)


async def send_approval_message(
    incident_id: str,
    title: str,
    hypothesis: str,
    action: str,
    blast_radius: str,
    confidence: float,
    retrieved_postmortem_id: str,
    slack_bot_token: Optional[str] = None,
    slack_channel_id: Optional[str] = None
) -> Optional[str]:
    """
    Posts an interactive approval request to Slack using Block Kit UI components.
    Includes LLM hypothesis, blast radius callout, confidence score, and Approve/Deny buttons.
    Returns the message ts (timestamp) if successful.
    """
    token = slack_bot_token or os.environ.get("SLACK_BOT_TOKEN")
    channel = slack_channel_id or os.environ.get("SLACK_CHANNEL_ID")

    if not token or not channel:
        logger.info(f"[SIMULATED SLACK MESSAGE] Token or Channel missing. Incident {incident_id} posted locally only.")
        return None

    confidence_pct = int(confidence * 100)
    
    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"🚨 [Approval Required] SRE Remediation: {incident_id}",
                "emoji": True
            }
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Incident:* {title}"},
                {"type": "mrkdwn", "text": f"*Confidence:* {confidence_pct}% (Medium Risk)"},
                {"type": "mrkdwn", "text": f"*Ref Postmortem:* `{retrieved_postmortem_id}`"},
                {"type": "mrkdwn", "text": f"*Autonomy Tier:* ✋ Escalated to Human"}
            ]
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*🤖 Root Cause Hypothesis:*\n>{hypothesis}"
            }
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*🔧 Proposed Remediation Plan:*\n`{action}`"
            }
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"⚠️ *Predicted Blast Radius:*\n_{blast_radius}_"
            }
        },
        {"type": "divider"},
        {
            "type": "actions",
            "block_id": f"approval_actions_{incident_id}",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "✅ Approve & Execute", "emoji": True},
                    "style": "primary",
                    "value": f"{incident_id}:approve",
                    "action_id": "btn_approve_incident"
                },
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "🛑 Deny & Escalate", "emoji": True},
                    "style": "danger",
                    "value": f"{incident_id}:deny",
                    "action_id": "btn_deny_incident"
                }
            ]
        }
    ]

    async with httpx.AsyncClient() as client:
        try:
            res = await client.post(
                "https://slack.com/api/chat.postMessage",
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "channel": channel,
                    "text": f"🚨 Human Approval Required for SRE Incident {incident_id}: {title}",
                    "blocks": blocks
                },
                timeout=10.0
            )
            data = res.json()
            if data.get("ok"):
                logger.info(f"Successfully posted Slack approval message for {incident_id}, ts: {data.get('ts')}")
                return data.get("ts")
            else:
                logger.error(f"Failed to post Slack message: {data.get('error')}")
                return None
        except Exception as e:
            logger.error(f"Error posting Slack message: {e}")
            return None


async def update_approval_message(
    response_url: str,
    incident_id: str,
    approved: bool,
    operator_name: str = "Operator"
) -> bool:
    """
    Updates the Slack interactive message via response_url when the user clicks Approve or Deny.
    """
    status_emoji = "✅" if approved else "🛑"
    status_text = f"{status_emoji} *Remediation {'APPROVED' if approved else 'DENIED'} by {operator_name}*"
    details = "Automated execution completed & verified successfully." if approved else "Execution canceled. Escalated to manual on-call triage."

    blocks = [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*{status_text}*\nIncident: `{incident_id}`\n_{details}_"
            }
        }
    ]

    async with httpx.AsyncClient() as client:
        try:
            res = await client.post(response_url, json={"replace_original": "true", "blocks": blocks}, timeout=10.0)
            return res.status_code == 200
        except Exception as e:
            logger.error(f"Error updating Slack message via response_url: {e}")
            return False
