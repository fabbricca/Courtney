"""
Authentication module for GLaDOS.

Provides JWT-based multi-user authentication with RBAC support.
"""

from .models import User, Role, Permission, Session
from .database import UserDatabase
from .jwt_handler import JWTHandler, TokenPayload
from .user_manager import UserManager
from .protocol import (
    AUTH_REQUEST,
    AUTH_RESPONSE_SUCCESS,
    AUTH_RESPONSE_FAILURE,
    AuthenticationMiddleware,
    ConnectionContext,
    has_permission,
)

__all__ = [
    "User",
    "Role",
    "Permission",
    "Session",
    "UserDatabase",
    "JWTHandler",
    "TokenPayload",
    "UserManager",
    "AUTH_REQUEST",
    "AUTH_RESPONSE_SUCCESS",
    "AUTH_RESPONSE_FAILURE",
    "AuthenticationMiddleware",
    "ConnectionContext",
    "has_permission",
]
