import hashlib
import os
import re

from bson import ObjectId
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status

from database import users_collection
from security.jwt_handler import get_current_user

router = APIRouter(prefix="/api/users", tags=["users"])


def user_to_response(user: dict) -> dict:
    """Convert MongoDB user document to API response."""
    return {
        "id": str(user["_id"]),
        "username": user.get("username"),
        "email": user.get("email"),
        "role": user.get("role"),
        "lastActiveAt": str(user.get("lastActiveAt", "")),
        "createdAt": str(user.get("createdAt", "")),
    }


def _require_admin(current_user: dict) -> None:
    """Raise 403 if the current user is not an admin."""
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")


@router.get("/profile/{user_id}")
async def get_user_profile(user_id: str, current_user: dict = Depends(get_current_user)):
    """Get user profile."""
    if not ObjectId.is_valid(user_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    user = await users_collection.find_one({"_id": ObjectId(user_id)})
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    return user_to_response(user)


@router.get("/search")
async def search_users(query: str):
    """Search users by username."""
    pattern = re.compile(re.escape(query), re.IGNORECASE)
    cursor = users_collection.find({"username": pattern})
    users = []
    async for user in cursor:
        users.append(user_to_response(user))
    return users


@router.get("/advanced-search")
async def advanced_search(
    username: str = None,
    email: str = None,
    role: str = None,
    sort_by: str = None,
    order: str = None,
):
    """Advanced user search with optional filters."""
    cursor = users_collection.find()
    all_users = []
    async for user in cursor:
        all_users.append(user)

    filtered = []
    for user in all_users:
        username_match = username is None or username.lower() in user.get("username", "").lower()
        email_match = email is None or email.lower() in user.get("email", "").lower()
        role_match = role is None or user.get("role") == role
        if username_match and email_match and role_match:
            filtered.append(user_to_response(user))

    if sort_by:
        reverse = order is not None and order.lower() == "desc"
        filtered.sort(key=lambda u: u.get(sort_by, ""), reverse=reverse)

    return filtered


@router.post("/hash")
async def hash_data(request: dict):
    """Hash data using SHA-256."""
    data = request.get("data", "")
    digest = hashlib.sha256(data.encode()).hexdigest()
    return {"hash": digest, "algorithm": "SHA-256"}


@router.delete("/{user_id}")
async def delete_user(user_id: str, current_user: dict = Depends(get_current_user)):
    """Delete a user. Requires admin role."""
    _require_admin(current_user)

    if not ObjectId.is_valid(user_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    result = await users_collection.delete_one({"_id": ObjectId(user_id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    return {"message": "User deleted"}


@router.put("/{user_id}/role")
async def change_role(user_id: str, request: dict, current_user: dict = Depends(get_current_user)):
    """Change a user's role. Requires admin role."""
    _require_admin(current_user)

    if not ObjectId.is_valid(user_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    new_role = request.get("role")
    result = await users_collection.update_one(
        {"_id": ObjectId(user_id)},
        {"$set": {"role": new_role, "updatedAt": datetime.utcnow()}},
    )

    if result.matched_count == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    return {"message": "Role updated", "role": new_role}
