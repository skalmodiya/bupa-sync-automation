"""Agent API proxy routes.

Proxies requests to the BUPA Sync agent service and manages local logs.
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
from fastapi import APIRouter, Body, Depends

from audit import log_event
from config import Settings, get_settings

router = APIRouter()

TIMEOUT = 30.0
LOGS_DIR = Path(__file__).parent.parent / "data" / "agent_logs"


def _error(message: str, detail: str = "") -> dict:
    return {"error": message, "detail": detail}


def _resolve_agent_url(settings: Settings) -> str:
    """Resolve agent URL, replacing localhost with Docker service name in Docker mode."""
    url = settings.agent.url.rstrip("/")
    if os.environ.get("DEPLOYMENT_MODE") == "docker":
        # In Docker, localhost:5000 is unreachable; use the service name
        url = url.replace("http://localhost:5000", "http://bupa-sync-agent:5000")
    return url


def _save_invocation_log(request_body: dict, response_data: Any, status: str) -> None:
    """Save agent invocation log locally."""
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).isoformat()
    log_entry = {
        "timestamp": timestamp,
        "request": request_body,
        "response": response_data,
        "status": status,
    }
    log_file = LOGS_DIR / f"{timestamp.replace(':', '-').replace('.', '-')}.json"
    log_file.write_text(json.dumps(log_entry, indent=2, default=str), encoding="utf-8")


@router.get("/health")
async def agent_health(settings: Settings = Depends(get_settings)) -> Any:
    """Proxy to agent /health endpoint."""
    url = _resolve_agent_url(settings) + "/health"
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.get(url)
            if resp.status_code == 200:
                return resp.json()
            return _error(
                "Agent health check failed",
                f"Status {resp.status_code}: {resp.text[:200]}",
            )
    except httpx.ConnectError as e:
        return _error("Cannot reach agent", str(e))
    except Exception as e:
        return _error("Agent health check failed", str(e))


@router.get("/card")
async def agent_card(settings: Settings = Depends(get_settings)) -> Any:
    """Proxy to agent /.well-known/agent.json (agent card)."""
    url = _resolve_agent_url(settings) + "/.well-known/agent.json"
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.get(url)
            if resp.status_code == 200:
                return resp.json()
            return _error(
                "Failed to fetch agent card",
                f"Status {resp.status_code}: {resp.text[:200]}",
            )
    except httpx.ConnectError as e:
        return _error("Cannot reach agent", str(e))
    except Exception as e:
        return _error("Agent card fetch failed", str(e))


@router.post("/invoke")
async def invoke_agent(
    payload: dict[str, Any] = Body(...),
    settings: Settings = Depends(get_settings),
) -> Any:
    """Proxy a message to the agent /invoke endpoint and log the interaction."""
    url = _resolve_agent_url(settings) + "/invoke"

    # Transform dashboard payload {"message": "..."} to A2A format {"messages": [...]}
    if "message" in payload and "messages" not in payload:
        agent_payload = {"messages": [{"role": "user", "content": payload["message"]}]}
    else:
        agent_payload = payload

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(url, json=agent_payload)
            if resp.status_code in (200, 201):
                response_data = resp.json()
                _save_invocation_log(payload, response_data, "success")
                message_preview = payload.get("message", "")[:100]
                log_event(
                    action="agent.invoked",
                    category="agent",
                    details={"message_preview": message_preview, "status": "success"},
                )
                return response_data
            error_text = resp.text[:500]
            _save_invocation_log(
                payload, {"status_code": resp.status_code, "body": error_text}, "error"
            )
            message_preview = payload.get("message", "")[:100]
            log_event(
                action="agent.invoked",
                category="agent",
                details={
                    "message_preview": message_preview,
                    "status": "error",
                    "status_code": resp.status_code,
                },
            )
            return _error(
                "Agent invocation failed", f"Status {resp.status_code}: {error_text}"
            )
    except httpx.ConnectError as e:
        _save_invocation_log(payload, {"error": str(e)}, "connection_error")
        message_preview = payload.get("message", "")[:100]
        log_event(
            action="agent.invoked",
            category="agent",
            details={
                "message_preview": message_preview,
                "status": "connection_error",
                "error": str(e),
            },
        )
        return _error("Cannot reach agent", str(e))
    except Exception as e:
        _save_invocation_log(payload, {"error": str(e)}, "exception")
        message_preview = payload.get("message", "")[:100]
        log_event(
            action="agent.invoked",
            category="agent",
            details={
                "message_preview": message_preview,
                "status": "exception",
                "error": str(e),
            },
        )
        return _error("Agent invocation failed", str(e))


@router.get("/logs")
async def get_agent_logs(limit: int = 50) -> Any:
    """Read agent invocation logs stored locally."""
    if not LOGS_DIR.exists():
        return {"logs": [], "total": 0}

    log_files = sorted(LOGS_DIR.glob("*.json"), reverse=True)[:limit]
    logs = []
    for log_file in log_files:
        try:
            data = json.loads(log_file.read_text(encoding="utf-8"))
            logs.append(data)
        except (json.JSONDecodeError, IOError):
            continue

    return {"logs": logs, "total": len(list(LOGS_DIR.glob("*.json")))}


@router.get("/info")
async def agent_info(settings: Settings = Depends(get_settings)) -> Any:
    """Return agent card info (alias for /card used by dashboard)."""
    url = _resolve_agent_url(settings) + "/.well-known/agent.json"
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.get(url)
            if resp.status_code == 200:
                return resp.json()
            return _error(
                "Failed to fetch agent info",
                f"Status {resp.status_code}: {resp.text[:200]}",
            )
    except httpx.ConnectError as e:
        return _error("Cannot reach agent", str(e))
    except Exception as e:
        return _error("Agent info fetch failed", str(e))


@router.get("/invocations")
async def get_invocations(limit: int = 20) -> list[dict]:
    """Return recent agent invocations (from local logs) in dashboard format."""
    if not LOGS_DIR.exists():
        return []

    log_files = sorted(LOGS_DIR.glob("*.json"), reverse=True)[:limit]
    invocations = []
    for log_file in log_files:
        try:
            data = json.loads(log_file.read_text(encoding="utf-8"))
            invocations.append(
                {
                    "id": log_file.stem,
                    "timestamp": data.get("timestamp", ""),
                    "message": data.get("request", {}).get("message", ""),
                    "response": data.get("response", {}).get(
                        "content", str(data.get("response", ""))
                    ),
                    "duration": data.get("duration", 0),
                    "tokenUsage": data.get(
                        "tokenUsage", {"prompt": 0, "completion": 0, "total": 0}
                    ),
                    "status": data.get("status", "unknown"),
                }
            )
        except (json.JSONDecodeError, IOError):
            continue

    return invocations


@router.delete("/invocations")
async def clear_invocations() -> dict:
    """Clear all agent invocation logs."""
    if not LOGS_DIR.exists():
        return {"status": "cleared", "count": 0}

    log_files = list(LOGS_DIR.glob("*.json"))
    count = len(log_files)
    for f in log_files:
        f.unlink(missing_ok=True)

    return {"status": "cleared", "count": count}
