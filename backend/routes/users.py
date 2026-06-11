"""Users routes — list and view app users (auto-registered on IAS login)."""

from fastapi import APIRouter

from database import list_app_users, get_app_user

router = APIRouter()


@router.get("")
async def get_users():
    """List all registered app users."""
    users = list_app_users()
    # Parse groups JSON for each user
    import json

    for u in users:
        try:
            u["groups"] = json.loads(u.get("groups", "[]"))
        except (json.JSONDecodeError, TypeError):
            u["groups"] = []
    return {"users": users, "total": len(users)}


@router.get("/{user_id}")
async def get_user(user_id: str):
    """Get a specific user's details."""
    import json

    user = get_app_user(user_id)
    if not user:
        return {"error": "User not found"}
    try:
        user["groups"] = json.loads(user.get("groups", "[]"))
    except (json.JSONDecodeError, TypeError):
        user["groups"] = []
    return user
