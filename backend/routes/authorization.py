"""Authorization routes — IAS group mapping, SCIM proxy, role resolution.

Provides:
- GET /api/authz/roles — list predefined roles and their permissions
- GET /api/authz/config — get current role-to-group mapping
- PUT /api/authz/config — update role-to-group mapping
- GET /api/authz/groups — list IAS groups (via SCIM API, read-only)
- GET /api/authz/groups/{id}/members — list members of an IAS group
- GET /api/authz/my-role — get current user's resolved role
"""

from typing import Any

import httpx
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from config import (
    AuthorizationConfig,
    Settings,
    get_settings,
    load_settings,
    save_settings,
)
from auth import get_optional_user
from database import get_setting, set_setting

router = APIRouter()

TIMEOUT = 15.0

# Predefined roles with permission definitions
ROLES = [
    {
        "id": "super_admin",
        "name": "Super Admin",
        "description": "Full access including authorization settings and danger zone",
        "permissions": [
            "view_dashboard",
            "view_records",
            "view_workflows",
            "view_audit",
            "view_agent",
            "trigger_sync",
            "trigger_retry",
            "trigger_agent_fix",
            "manage_settings",
            "manage_authorization",
            "danger_zone",
        ],
    },
    {
        "id": "admin",
        "name": "Admin",
        "description": "Manage settings and all operational features",
        "permissions": [
            "view_dashboard",
            "view_records",
            "view_workflows",
            "view_audit",
            "view_agent",
            "trigger_sync",
            "trigger_retry",
            "trigger_agent_fix",
            "manage_settings",
        ],
    },
    {
        "id": "editor",
        "name": "Editor",
        "description": "View data and trigger sync/retry/agent operations",
        "permissions": [
            "view_dashboard",
            "view_records",
            "view_workflows",
            "view_audit",
            "view_agent",
            "trigger_sync",
            "trigger_retry",
            "trigger_agent_fix",
        ],
    },
    {
        "id": "viewer",
        "name": "Viewer",
        "description": "Read-only access to dashboard, records, workflows, and audit log",
        "permissions": [
            "view_dashboard",
            "view_records",
            "view_workflows",
            "view_audit",
            "view_agent",
        ],
    },
]


def resolve_user_role(user_groups: list[str], settings: Settings) -> dict:
    """Resolve the highest role for a user based on their IAS groups.

    Priority: super_admin > admin > editor > viewer.
    Returns role dict or None if no matching group.
    """
    authz = settings.authorization
    if not authz.enabled:
        # Authorization disabled — everyone gets super_admin
        return ROLES[0]

    # Check from highest to lowest priority
    if authz.super_admin_group and authz.super_admin_group in user_groups:
        return ROLES[0]
    if authz.admin_group and authz.admin_group in user_groups:
        return ROLES[1]
    if authz.editor_group and authz.editor_group in user_groups:
        return ROLES[2]
    if authz.viewer_group and authz.viewer_group in user_groups:
        return ROLES[3]

    return {
        "id": "none",
        "name": "No Access",
        "description": "No role assigned",
        "permissions": [],
    }


def user_has_permission(
    user_groups: list[str], permission: str, settings: Settings
) -> bool:
    """Check if user has a specific permission based on their groups."""
    role = resolve_user_role(user_groups, settings)
    return permission in role.get("permissions", [])


def _scim_headers(settings: Settings) -> dict[str, str]:
    """Build auth headers for IAS SCIM API using dedicated SCIM credentials."""
    import base64

    authz = settings.authorization
    # Use dedicated SCIM credentials if configured, else fall back to OIDC client
    user = authz.scim_user or settings.auth.client_id
    password = authz.scim_password or settings.auth.client_secret

    if not user or not password:
        return {}
    creds = base64.b64encode(f"{user}:{password}".encode()).decode()
    return {
        "Authorization": f"Basic {creds}",
        "Content-Type": "application/scim+json",
    }


def _scim_base_url(settings: Settings) -> str:
    """Get SCIM API base URL — uses dedicated URL if set, else derives from IAS URL."""
    if settings.authorization.scim_url:
        return settings.authorization.scim_url.rstrip("/")
    return settings.auth.ias_url.rstrip("/") + "/scim"


# --- Endpoints ---


@router.get("/roles")
async def list_roles():
    """List all predefined roles and their permissions."""
    return {"roles": ROLES}


@router.get("/config")
async def get_authz_config(settings: Settings = Depends(get_settings)):
    """Get current authorization configuration (role-to-group mapping)."""
    return settings.authorization.model_dump()


@router.put("/config")
async def update_authz_config(payload: AuthorizationConfig, request: Request):
    """Update authorization configuration (role-to-group mapping)."""
    user = get_optional_user(request)
    settings = load_settings()

    # Only super_admins can change authorization (or anyone if authz is disabled)
    if settings.authorization.enabled:
        user_groups = _get_user_groups(request, settings)
        if not user_has_permission(user_groups, "manage_authorization", settings):
            return JSONResponse(
                {
                    "error": "Forbidden",
                    "detail": "Only Super Admins can manage authorization",
                },
                status_code=403,
            )

    settings.authorization = payload
    save_settings(settings, user=user.get("user_id", "system"))
    return {"status": "saved"}


@router.get("/groups")
async def list_ias_groups(settings: Settings = Depends(get_settings)):
    """Fetch all IAS groups via SCIM API (read-only)."""
    if not settings.authorization.scim_url and not settings.auth.ias_url:
        return {"error": "SCIM URL not configured. Enter the SCIM API URL."}

    url = _scim_base_url(settings) + "/Groups?count=100"
    headers = _scim_headers(settings)
    if not headers:
        return {"error": "SCIM credentials not configured"}

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.get(url, headers=headers)
            if resp.status_code == 200:
                data = resp.json()
                groups = [
                    {
                        "id": g.get("id", ""),
                        "displayName": g.get("displayName", ""),
                    }
                    for g in data.get("Resources", [])
                ]
                return {
                    "groups": groups,
                    "total": data.get("totalResults", len(groups)),
                }
            return {
                "error": f"SCIM API error: {resp.status_code}",
                "detail": resp.text[:300],
            }
    except Exception as e:
        return {"error": "Cannot reach IAS SCIM API", "detail": str(e)}


@router.get("/groups/{group_id}/members")
async def get_group_members(group_id: str, settings: Settings = Depends(get_settings)):
    """Fetch members of a specific IAS group via SCIM API (read-only)."""
    if not settings.authorization.scim_url and not settings.auth.ias_url:
        return {"error": "SCIM URL not configured"}

    url = (
        _scim_base_url(settings) + f"/Groups/{group_id}?attributes=displayName,members"
    )
    headers = _scim_headers(settings)
    if not headers:
        return {"error": "IAS credentials not configured"}

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.get(url, headers=headers)
            if resp.status_code == 200:
                data = resp.json()
                members = [
                    {
                        "value": m.get("value", ""),
                        "display": m.get("display", ""),
                        "type": m.get("type", ""),
                    }
                    for m in data.get("members", [])
                ]
                return {
                    "group_id": group_id,
                    "displayName": data.get("displayName", ""),
                    "members": members,
                    "total": len(members),
                }
            return {
                "error": f"SCIM API error: {resp.status_code}",
                "detail": resp.text[:300],
            }
    except Exception as e:
        return {"error": "Cannot reach IAS SCIM API", "detail": str(e)}


@router.get("/my-role")
async def get_my_role(request: Request, settings: Settings = Depends(get_settings)):
    """Get the current user's resolved role based on their IAS groups."""
    user_groups = _get_user_groups(request, settings)
    role = resolve_user_role(user_groups, settings)
    return {
        "role": role,
        "groups": user_groups,
        "authorization_enabled": settings.authorization.enabled,
    }


def _get_user_groups(request: Request, settings: Settings) -> list[str]:
    """Extract user's IAS groups from session or token."""
    from database import get_session

    session_id = request.cookies.get("session_id")
    if not session_id:
        return []

    session = get_session(session_id)
    if not session:
        return []

    # Groups are stored during login callback in the session
    # or can be fetched from the userinfo endpoint
    # For now, fetch from IAS userinfo if access_token is available
    # Cache in session to avoid repeated calls
    groups_raw = session.get("groups", "")
    if groups_raw:
        import json

        try:
            return json.loads(groups_raw)
        except (json.JSONDecodeError, TypeError):
            return []

    return []
