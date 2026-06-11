"""Authentication routes for SAP IAS OIDC flow."""

import secrets
import urllib.parse
from typing import Any

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse, JSONResponse

from config import load_settings
from database import create_session, get_session, delete_session, upsert_app_user
from auth import decode_token

router = APIRouter()


def _get_request_origin(request: Request) -> str:
    """Derive the origin (scheme + host) from the incoming request."""
    # Use X-Forwarded headers if behind a proxy, otherwise use the Host header
    forwarded_proto = request.headers.get("x-forwarded-proto", "http")
    forwarded_host = request.headers.get("x-forwarded-host") or request.headers.get(
        "host", "localhost:3001"
    )
    # The request arrives at the backend on port 8080, but the user accesses
    # via the dashboard nginx on port 3001 (or 80 inside Docker).
    # The Host header from nginx proxy contains the original host the user used.
    return f"{forwarded_proto}://{forwarded_host}"


def _build_redirect_uri(request: Request, settings) -> str:
    """Build the OIDC redirect URI dynamically from the request origin."""
    origin = _get_request_origin(request)
    return f"{origin}/api/auth/callback"


@router.get("/login")
async def login(request: Request):
    """Redirect to IAS authorization endpoint."""
    settings = load_settings()
    if not settings.auth.ias_url or not settings.auth.client_id:
        return JSONResponse(
            {"error": "IAS not configured. Configure in Settings → Auth tab."},
            status_code=400,
        )

    state = secrets.token_urlsafe(32)
    # Dynamically build redirect_uri from the request origin so it works from any host
    redirect_uri = _build_redirect_uri(request, settings)
    params = {
        "response_type": "code",
        "client_id": settings.auth.client_id,
        "redirect_uri": redirect_uri,
        "scope": "openid email profile groups",
        "state": state,
    }
    auth_url = (
        f"{settings.auth.ias_url}/oauth2/authorize?{urllib.parse.urlencode(params)}"
    )
    response = RedirectResponse(url=auth_url)
    response.set_cookie(
        "oauth_state", state, httponly=True, max_age=600, samesite="lax"
    )
    # Store the redirect_uri used so the callback can use the same one for token exchange
    response.set_cookie(
        "oauth_redirect_uri", redirect_uri, httponly=True, max_age=600, samesite="lax"
    )
    return response


@router.get("/callback")
async def callback(request: Request, code: str = "", state: str = "", error: str = ""):
    """Handle IAS callback with authorization code."""
    if error:
        return JSONResponse({"error": f"IAS error: {error}"}, status_code=400)

    settings = load_settings()

    # Use the same redirect_uri that was sent in the login request
    redirect_uri = request.cookies.get("oauth_redirect_uri") or _build_redirect_uri(
        request, settings
    )

    # Exchange code for token
    token_url = f"{settings.auth.ias_url}/oauth2/token"
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            token_url,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
                "client_id": settings.auth.client_id,
                "client_secret": settings.auth.client_secret,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

    if resp.status_code != 200:
        return JSONResponse(
            {"error": f"Token exchange failed: {resp.text}"}, status_code=400
        )

    token_data = resp.json()
    id_token = token_data.get("id_token", "")
    access_token = token_data.get("access_token", "")

    # Decode ID token to get user info
    user_info = decode_token(id_token, settings.auth.ias_url, settings.auth.client_id)

    # Fetch groups from userinfo endpoint
    user_groups: list[str] = []
    try:
        async with httpx.AsyncClient(timeout=10.0) as userinfo_client:
            userinfo_resp = await userinfo_client.get(
                f"{settings.auth.ias_url}/oauth2/userinfo",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            if userinfo_resp.status_code == 200:
                userinfo_data = userinfo_resp.json()
                user_groups = userinfo_data.get("groups", [])
    except Exception:
        pass  # Groups will be empty if userinfo fails

    import json as _json

    # Create session
    session_id = secrets.token_urlsafe(32)
    create_session(
        session_id=session_id,
        user_id=user_info.get("sub", "unknown"),
        user_name=user_info.get("name", user_info.get("given_name", "User")),
        user_email=user_info.get("email", ""),
        access_token=access_token,
        groups=_json.dumps(user_groups),
        expires_at=str(token_data.get("expires_in", "3600")),
    )

    # Auto-register/update app user record
    upsert_app_user(
        user_id=user_info.get("sub", "unknown"),
        display_name=user_info.get("name", user_info.get("given_name", "User")),
        email=user_info.get("email", ""),
        given_name=user_info.get("given_name", ""),
        family_name=user_info.get("family_name", ""),
        groups=_json.dumps(user_groups),
    )

    # Redirect to dashboard with session cookie
    response = RedirectResponse(url="/")
    response.set_cookie(
        "session_id", session_id, httponly=True, max_age=3600, samesite="lax"
    )
    response.delete_cookie("oauth_state")
    return response


@router.get("/me")
async def get_me(request: Request):
    """Get current authenticated user info."""
    from auth import get_optional_user

    user = get_optional_user(request)
    return user


@router.post("/logout")
async def logout(request: Request):
    """Logout - destroy session and redirect to IAS logout."""
    settings = load_settings()
    session_id = request.cookies.get("session_id")
    if session_id:
        delete_session(session_id)

    # Build IAS logout URL using the request origin
    ias_logout_url = ""
    if settings.auth.ias_url:
        origin = _get_request_origin(request)
        params = urllib.parse.urlencode(
            {
                "post_logout_redirect_uri": origin,
                "client_id": settings.auth.client_id,
            }
        )
        ias_logout_url = f"{settings.auth.ias_url}/oauth2/logout?{params}"

    response = JSONResponse(
        {
            "status": "logged_out",
            "ias_logout_url": ias_logout_url,
        }
    )
    response.delete_cookie("session_id")
    response.delete_cookie("oauth_redirect_uri")
    return response


@router.get("/profile")
async def get_profile(request: Request):
    """Get detailed profile info for the current user from IAS userinfo endpoint."""
    settings = load_settings()
    session_id = request.cookies.get("session_id")
    if not session_id:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)

    session = get_session(session_id)
    if not session:
        return JSONResponse({"error": "Session expired"}, status_code=401)

    # Call IAS userinfo endpoint with access token
    profile = {
        "user_id": session["user_id"],
        "name": session["user_name"],
        "email": session["user_email"],
        "raw_userinfo": None,
    }

    if settings.auth.ias_url and session.get("access_token"):
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    f"{settings.auth.ias_url}/oauth2/userinfo",
                    headers={"Authorization": f"Bearer {session['access_token']}"},
                )
                if resp.status_code == 200:
                    userinfo = resp.json()
                    profile["raw_userinfo"] = userinfo
                    profile.update(
                        {
                            "name": userinfo.get("name", profile["name"]),
                            "email": userinfo.get("email", profile["email"]),
                            "given_name": userinfo.get("given_name", ""),
                            "family_name": userinfo.get("family_name", ""),
                            "global_user_id": userinfo.get(
                                "user_uuid",
                                userinfo.get("global_user_id", userinfo.get("sub", "")),
                            ),
                            "groups": userinfo.get("groups", []),
                            "ias_tenant": settings.auth.ias_url,
                        }
                    )
                else:
                    profile["_userinfo_error"] = (
                        f"IAS returned {resp.status_code}: {resp.text[:200]}"
                    )
        except Exception as e:
            profile["_userinfo_error"] = f"Failed to fetch userinfo: {str(e)}"

    return profile


@router.get("/status")
async def auth_status(request: Request):
    """Check if IAS is configured and if user is authenticated."""
    settings = load_settings()
    ias_configured = bool(settings.auth.ias_url and settings.auth.client_id)

    session_id = request.cookies.get("session_id")
    authenticated = False
    user = None
    if session_id:
        session = get_session(session_id)
        if session:
            authenticated = True
            user = {"name": session["user_name"], "email": session["user_email"]}

    return {
        "ias_configured": ias_configured,
        "authenticated": authenticated,
        "user": user,
        "login_url": "/api/auth/login" if ias_configured else None,
    }
