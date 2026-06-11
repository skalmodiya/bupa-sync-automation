"""Settings CRUD, connectivity test, and dynamic dropdown endpoints."""

import json
import smtplib
from typing import Any

import httpx
from fastapi import APIRouter, Body, Depends, Request

from audit import log_event
from auth import get_optional_user
from config import Settings, get_settings, load_settings, mask_settings, save_settings
from database import get_setting, set_setting

router = APIRouter()

TIMEOUT = 30.0


def _error(message: str, detail: str = "") -> dict:
    return {"error": message, "detail": detail}


@router.get("")
async def get_all_settings(settings: Settings = Depends(get_settings)) -> dict:
    """Return current settings with API keys masked."""
    return mask_settings(settings)


@router.put("")
async def update_settings(payload: Settings, request: Request) -> dict:
    """Save all settings. Preserves existing API keys if masked values are submitted."""
    user = get_optional_user(request)
    # Load current settings to preserve real API keys when masked values come in
    current = load_settings()

    # If the incoming API key looks masked (all * except last 4), keep the existing one
    def preserve_if_masked(new_val: str, old_val: str) -> str:
        if not new_val:
            return ""  # Explicitly cleared
        if new_val.startswith("*") and len(new_val) > 4:
            return old_val  # Masked value submitted, keep original
        return new_val  # Real new value

    payload.llm.api_key = preserve_if_masked(payload.llm.api_key, current.llm.api_key)
    payload.n8n.api_key = preserve_if_masked(payload.n8n.api_key, current.n8n.api_key)
    payload.smtp.password = preserve_if_masked(
        payload.smtp.password, current.smtp.password
    )
    payload.auth.client_secret = preserve_if_masked(
        payload.auth.client_secret, current.auth.client_secret
    )

    save_settings(payload, user=user["user_id"])
    log_event(
        action="settings.updated",
        category="settings",
        user=user["user_id"],
        user_name=user["name"],
        user_email=user["email"],
        details={
            "sections_changed": ["llm", "n8n", "smtp", "mock_s4", "agent", "auth"]
        },
    )
    return {"status": "saved"}


@router.post("/test-llm")
async def test_llm_connection(
    request: Request, payload: Settings | None = None
) -> dict:
    """Test LLM connection by calling the /models endpoint."""
    user = get_optional_user(request)
    saved = load_settings()
    settings = payload or saved
    # Resolve masked API key: if payload has a masked key, use the saved real one
    if settings.llm.api_key and settings.llm.api_key.startswith("*"):
        settings.llm.api_key = saved.llm.api_key
    url = settings.llm.base_url.rstrip("/") + "/models"
    headers: dict[str, str] = {}
    if settings.llm.api_key and not settings.llm.api_key.startswith("*"):
        headers["Authorization"] = f"Bearer {settings.llm.api_key}"
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.get(url, headers=headers)
            if resp.status_code == 200:
                data = resp.json()
                models = data.get("data", [])
                model_ids = [m.get("id", "unknown") for m in models[:10]]
                log_event(
                    action="settings.test_connection",
                    category="settings",
                    user=user["user_id"],
                    user_name=user["name"],
                    user_email=user["email"],
                    details={"type": "llm", "result": "success"},
                )
                return {"status": "connected", "models": model_ids}
            log_event(
                action="settings.test_connection",
                category="settings",
                user=user["user_id"],
                user_name=user["name"],
                user_email=user["email"],
                details={
                    "type": "llm",
                    "result": "failed",
                    "status_code": resp.status_code,
                },
            )
            return _error(
                "LLM connection failed",
                f"Status {resp.status_code}: {resp.text[:200]}",
            )
    except httpx.ConnectError as e:
        log_event(
            action="settings.test_connection",
            category="settings",
            user=user["user_id"],
            user_name=user["name"],
            user_email=user["email"],
            details={"type": "llm", "result": "error", "error": str(e)},
        )
        return _error("Cannot reach LLM endpoint", str(e))
    except Exception as e:
        log_event(
            action="settings.test_connection",
            category="settings",
            user=user["user_id"],
            user_name=user["name"],
            user_email=user["email"],
            details={"type": "llm", "result": "error", "error": str(e)},
        )
        return _error("LLM test failed", str(e))


@router.post("/test-n8n")
async def test_n8n_connection(
    request: Request, payload: Settings | None = None
) -> dict:
    """Test n8n connection by listing workflows."""
    user = get_optional_user(request)
    saved = load_settings()
    settings = payload or saved
    # Resolve masked API key: if payload has a masked key, use the saved real one
    if settings.n8n.api_key and settings.n8n.api_key.startswith("*"):
        settings.n8n.api_key = saved.n8n.api_key
    url = settings.n8n.url.rstrip("/") + "/api/v1/workflows"
    headers: dict[str, str] = {}
    if settings.n8n.api_key and not settings.n8n.api_key.startswith("*"):
        headers["X-N8N-API-KEY"] = settings.n8n.api_key
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.get(url, headers=headers)
            if resp.status_code == 200:
                data = resp.json()
                count = len(data.get("data", []))
                log_event(
                    action="settings.test_connection",
                    category="settings",
                    user=user["user_id"],
                    user_name=user["name"],
                    user_email=user["email"],
                    details={
                        "type": "n8n",
                        "result": "success",
                        "workflow_count": count,
                    },
                )
                return {"status": "connected", "workflow_count": count}
            log_event(
                action="settings.test_connection",
                category="settings",
                user=user["user_id"],
                user_name=user["name"],
                user_email=user["email"],
                details={
                    "type": "n8n",
                    "result": "failed",
                    "status_code": resp.status_code,
                },
            )
            return _error(
                "n8n connection failed",
                f"Status {resp.status_code}: {resp.text[:200]}",
            )
    except httpx.ConnectError as e:
        log_event(
            action="settings.test_connection",
            category="settings",
            user=user["user_id"],
            user_name=user["name"],
            user_email=user["email"],
            details={"type": "n8n", "result": "error", "error": str(e)},
        )
        return _error("Cannot reach n8n", str(e))
    except Exception as e:
        log_event(
            action="settings.test_connection",
            category="settings",
            user=user["user_id"],
            user_name=user["name"],
            user_email=user["email"],
            details={"type": "n8n", "result": "error", "error": str(e)},
        )
        return _error("n8n test failed", str(e))


@router.post("/test-s4")
async def test_s4_connection(request: Request, payload: Settings | None = None) -> dict:
    """Test mock S/4HANA connection."""
    user = get_optional_user(request)
    settings = payload or load_settings()
    url = settings.mock_s4.url.rstrip("/") + "/api/pa0000"
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.get(url)
            if resp.status_code == 200:
                data = resp.json()
                count = (
                    len(data)
                    if isinstance(data, list)
                    else data.get("count", "unknown")
                )
                log_event(
                    action="settings.test_connection",
                    category="settings",
                    user=user["user_id"],
                    user_name=user["name"],
                    user_email=user["email"],
                    details={"type": "s4", "result": "success", "record_count": count},
                )
                return {"status": "connected", "record_count": count}
            log_event(
                action="settings.test_connection",
                category="settings",
                user=user["user_id"],
                user_name=user["name"],
                user_email=user["email"],
                details={
                    "type": "s4",
                    "result": "failed",
                    "status_code": resp.status_code,
                },
            )
            return _error(
                "Mock S/4 connection failed",
                f"Status {resp.status_code}: {resp.text[:200]}",
            )
    except httpx.ConnectError as e:
        log_event(
            action="settings.test_connection",
            category="settings",
            user=user["user_id"],
            user_name=user["name"],
            user_email=user["email"],
            details={"type": "s4", "result": "error", "error": str(e)},
        )
        return _error("Cannot reach mock S/4HANA", str(e))
    except Exception as e:
        log_event(
            action="settings.test_connection",
            category="settings",
            user=user["user_id"],
            user_name=user["name"],
            user_email=user["email"],
            details={"type": "s4", "result": "error", "error": str(e)},
        )
        return _error("Mock S/4 test failed", str(e))


@router.post("/test-agent")
async def test_agent_connection(
    request: Request, payload: Settings | None = None
) -> dict:
    """Test agent connection via /health endpoint."""
    import os

    user = get_optional_user(request)
    settings = payload or load_settings()
    agent_url = settings.agent.url.rstrip("/")
    # In Docker, resolve localhost to Docker service name
    if os.environ.get("DEPLOYMENT_MODE") == "docker":
        agent_url = agent_url.replace(
            "http://localhost:5000", "http://bupa-sync-agent:5000"
        )
    url = agent_url + "/health"
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.get(url)
            if resp.status_code == 200:
                log_event(
                    action="settings.test_connection",
                    category="settings",
                    user=user["user_id"],
                    user_name=user["name"],
                    user_email=user["email"],
                    details={"type": "agent", "result": "success"},
                )
                return {"status": "connected", "agent_response": resp.json()}
            log_event(
                action="settings.test_connection",
                category="settings",
                user=user["user_id"],
                user_name=user["name"],
                user_email=user["email"],
                details={
                    "type": "agent",
                    "result": "failed",
                    "status_code": resp.status_code,
                },
            )
            return _error(
                "Agent connection failed",
                f"Status {resp.status_code}: {resp.text[:200]}",
            )
    except httpx.ConnectError as e:
        log_event(
            action="settings.test_connection",
            category="settings",
            user=user["user_id"],
            user_name=user["name"],
            user_email=user["email"],
            details={"type": "agent", "result": "error", "error": str(e)},
        )
        return _error("Cannot reach agent", str(e))
    except Exception as e:
        log_event(
            action="settings.test_connection",
            category="settings",
            user=user["user_id"],
            user_name=user["name"],
            user_email=user["email"],
            details={"type": "agent", "result": "error", "error": str(e)},
        )
        return _error("Agent test failed", str(e))


@router.post("/test-smtp")
async def test_smtp_connection(
    request: Request, payload: Settings | None = None
) -> dict:
    """Test SMTP connectivity."""
    import asyncio

    user = get_optional_user(request)
    settings = payload or load_settings()

    def _test_smtp():
        smtp = smtplib.SMTP(settings.smtp.host, settings.smtp.port, timeout=5)
        smtp.ehlo()
        if settings.smtp.username and settings.smtp.password:
            smtp.login(settings.smtp.username, settings.smtp.password)
        smtp.quit()

    try:
        await asyncio.to_thread(_test_smtp)
        log_event(
            action="settings.test_connection",
            category="settings",
            user=user["user_id"],
            user_name=user["name"],
            user_email=user["email"],
            details={"type": "smtp", "result": "success"},
        )
        return {"status": "connected"}
    except smtplib.SMTPAuthenticationError as e:
        log_event(
            action="settings.test_connection",
            category="settings",
            user=user["user_id"],
            user_name=user["name"],
            user_email=user["email"],
            details={"type": "smtp", "result": "auth_error", "error": str(e)},
        )
        return _error("SMTP authentication failed", str(e))
    except (ConnectionRefusedError, OSError, TimeoutError) as e:
        log_event(
            action="settings.test_connection",
            category="settings",
            user=user["user_id"],
            user_name=user["name"],
            user_email=user["email"],
            details={"type": "smtp", "result": "error", "error": str(e)},
        )
        return _error("Cannot reach SMTP server", str(e))
    except Exception as e:
        log_event(
            action="settings.test_connection",
            category="settings",
            user=user["user_id"],
            user_name=user["name"],
            user_email=user["email"],
            details={"type": "smtp", "result": "error", "error": str(e)},
        )
        return _error("SMTP test failed", str(e))


@router.post("/send-test-email")
async def send_test_email(request: Request, payload: Settings | None = None) -> dict:
    """Send an actual test email via SMTP to verify end-to-end delivery."""
    import asyncio
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart
    from datetime import datetime

    settings = payload or load_settings()

    def _send():
        msg = MIMEMultipart()
        msg["From"] = "bupa-sync-agent@local.test"
        msg["To"] = "admin@local.test"
        msg["Subject"] = (
            f"BUPA Sync - Test Email ({datetime.now().strftime('%H:%M:%S')})"
        )

        body = """
        <h2>BUPA Sync Automation - Test Email</h2>
        <p>This is a test email sent from the BUPA Sync Dashboard settings page.</p>
        <p>If you can see this in Mailpit, your email configuration is working correctly.</p>
        <hr>
        <p><strong>SMTP Host:</strong> {host}:{port}</p>
        <p><strong>Sent at:</strong> {time}</p>
        """.format(
            host=settings.smtp.host,
            port=settings.smtp.port,
            time=datetime.now().isoformat(),
        )

        msg.attach(MIMEText(body, "html"))

        smtp = smtplib.SMTP(settings.smtp.host, settings.smtp.port, timeout=5)
        smtp.ehlo()
        if settings.smtp.username and settings.smtp.password:
            smtp.login(settings.smtp.username, settings.smtp.password)
        smtp.sendmail(
            "bupa-sync-agent@local.test", ["admin@local.test"], msg.as_string()
        )
        smtp.quit()

    try:
        await asyncio.to_thread(_send)
        return {
            "status": "sent",
            "message": "Test email sent to admin@local.test. Check Mailpit at http://localhost:8025",
        }
    except Exception as e:
        return _error("Failed to send test email", str(e))


# --- Dynamic Dropdown Endpoints ---


@router.post("/fetch-n8n-workflows")
async def fetch_n8n_workflows(
    request: Request, payload: Settings | None = None
) -> dict:
    """Fetch available workflows from n8n for the dropdown."""
    # Use payload if it has a real API key, otherwise fall back to saved settings
    saved = load_settings()
    settings = (
        payload
        if (payload and payload.n8n.api_key and not payload.n8n.api_key.startswith("*"))
        else saved
    )
    if not settings.n8n.api_key or settings.n8n.api_key.startswith("*"):
        return _error("n8n API key required", "Enter your API key first")
    url = settings.n8n.url.rstrip("/") + "/api/v1/workflows"
    headers = {"X-N8N-API-KEY": settings.n8n.api_key}
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.get(url, headers=headers)
            if resp.status_code == 200:
                data = resp.json()
                workflows = data.get("data", [])
                return {
                    "workflows": [
                        {
                            "id": w["id"],
                            "name": w["name"],
                            "active": w.get("active", False),
                        }
                        for w in workflows
                    ]
                }
            return _error("Failed to fetch workflows", f"Status {resp.status_code}")
    except Exception as e:
        return _error("Cannot reach n8n", str(e))


@router.post("/fetch-llm-models")
async def fetch_llm_models(request: Request, payload: Settings | None = None) -> dict:
    """Fetch available models from LLM provider for the dropdown."""
    # Use payload if it has a real API key, otherwise fall back to saved settings
    saved = load_settings()
    settings = (
        payload
        if (payload and payload.llm.api_key and not payload.llm.api_key.startswith("*"))
        else saved
    )
    url = settings.llm.base_url.rstrip("/") + "/models"
    headers: dict[str, str] = {}
    if settings.llm.api_key and not settings.llm.api_key.startswith("*"):
        headers["Authorization"] = f"Bearer {settings.llm.api_key}"
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.get(url, headers=headers)
            if resp.status_code == 200:
                data = resp.json()
                models = data.get("data", [])
                return {
                    "models": [
                        {"id": m.get("id", ""), "name": m.get("id", "Unknown")}
                        for m in models
                    ]
                }
            return _error("Failed to fetch models", f"Status {resp.status_code}")
    except Exception as e:
        return _error("Cannot reach LLM", str(e))


# --- Dashboard Configuration ---

DASHBOARD_CONFIG_KEY = "dashboard_config"


@router.get("/dashboard")
async def get_dashboard_config() -> dict:
    """Return stored dashboard configuration (plain JSON dict, frontend owns schema)."""
    raw = get_setting(DASHBOARD_CONFIG_KEY, "")
    if raw:
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            return {}
    return {}


@router.put("/dashboard")
async def save_dashboard_config(request: Request, config: Any = Body(...)) -> dict:
    """Save dashboard configuration. Accepts any JSON object — frontend owns the schema."""
    user = get_optional_user(request)
    set_setting(DASHBOARD_CONFIG_KEY, json.dumps(config), user=user["user_id"])
    log_event(
        action="settings.dashboard_updated",
        category="settings",
        user=user["user_id"],
        user_name=user["name"],
        user_email=user["email"],
        details={"action": "dashboard_config_saved"},
    )
    return {"status": "saved"}


@router.post("/reset-app")
async def reset_app(request: Request, payload: dict = Body(...)) -> dict:
    """Reset selected parts of the application.

    payload: {
        "confirmation": "DELETE",  # Must be exactly "DELETE"
        "purpose": "...",          # Reason for reset (stored in audit permanently)
        "targets": ["audit_log", "jobs", "agent_logs", "sync_history", "settings", "sessions"]
    }

    The reset audit event itself can NEVER be deleted from UI.
    """
    from database import get_connection

    user = get_optional_user(request)

    confirmation = payload.get("confirmation", "")
    purpose = payload.get("purpose", "")
    targets = payload.get("targets", [])

    if confirmation != "DELETE":
        return {
            "error": "Invalid confirmation",
            "detail": "Type DELETE to confirm reset",
        }

    if not purpose or len(purpose) < 10:
        return {
            "error": "Purpose required",
            "detail": "Provide a reason (minimum 10 characters) for the reset",
        }

    if not targets:
        return {
            "error": "No targets selected",
            "detail": "Select at least one item to reset",
        }

    valid_targets = [
        "audit_log",
        "jobs",
        "agent_logs",
        "sync_history",
        "settings",
        "sessions",
    ]
    invalid = [t for t in targets if t not in valid_targets]
    if invalid:
        return {
            "error": f"Invalid targets: {invalid}",
            "detail": f"Valid targets: {valid_targets}",
        }

    # First, log the reset event (this can never be deleted)
    reset_event = log_event(
        action="system.app_reset",
        category="system",
        user=user["user_id"],
        user_name=user["name"],
        user_email=user.get("email", ""),
        details={
            "targets": targets,
            "purpose": purpose,
            "protected": True,  # Marks this event as non-deletable
        },
    )

    results = {}

    with get_connection() as conn:
        if "audit_log" in targets:
            # Delete all audit events EXCEPT system.app_reset events
            cursor = conn.execute(
                "DELETE FROM audit_log WHERE NOT (action = 'system.app_reset' AND category = 'system')"
            )
            results["audit_log"] = (
                f"{cursor.rowcount} events deleted (reset events preserved)"
            )

        if "jobs" in targets:
            cursor = conn.execute("DELETE FROM jobs")
            results["jobs"] = f"{cursor.rowcount} jobs deleted"

        if "sessions" in targets:
            cursor = conn.execute("DELETE FROM sessions")
            results["sessions"] = "All sessions cleared"

        if "settings" in targets:
            # Reset settings to defaults (keep auth config so user stays logged in)
            current = load_settings()
            fresh = Settings()
            fresh.auth = current.auth  # Preserve auth so user doesn't get locked out
            save_settings(fresh, user=user["user_id"])
            results["settings"] = "Settings reset to defaults (auth preserved)"

        if "sync_history" in targets:
            # Clear sync history file
            from pathlib import Path

            history_file = Path(__file__).parent.parent / "data" / "sync_history.json"
            if history_file.exists():
                history_file.unlink()
            results["sync_history"] = "Sync history cleared"

        if "agent_logs" in targets:
            # Clear agent invocation logs
            import shutil
            from pathlib import Path

            logs_dir = Path(__file__).parent.parent / "data" / "agent_logs"
            if logs_dir.exists():
                count = len(list(logs_dir.glob("*.json")))
                shutil.rmtree(logs_dir)
                logs_dir.mkdir(parents=True, exist_ok=True)
                results["agent_logs"] = f"{count} invocation logs deleted"
            else:
                results["agent_logs"] = "No logs to delete"

    return {
        "status": "reset_complete",
        "results": results,
        "reset_event_id": reset_event.get("id", ""),
    }
