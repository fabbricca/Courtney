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
from .permissions import (
    Permission as PermissionEnum,
    Role as RoleEnum,
    PermissionChecker,
    PermissionDeniedError,
    check_permission,
    check_function_permission,
    require_permission,
    require_function_permission,
    ROLE_PERMISSIONS,
    FUNCTION_PERMISSIONS,
)

__all__ = [
    # User models and database
    "User",
    "Role",
    "Permission",
    "Session",
    "UserDatabase",
    # JWT handling
    "JWTHandler",
    "TokenPayload",
    "UserManager",
    # Protocol
    "AUTH_REQUEST",
    "AUTH_RESPONSE_SUCCESS",
    "AUTH_RESPONSE_FAILURE",
    "AuthenticationMiddleware",
    "ConnectionContext",
    "has_permission",
    # RBAC permissions (v2.1+)
    "PermissionEnum",
    "RoleEnum",
    "PermissionChecker",
    "PermissionDeniedError",
    "check_permission",
    "check_function_permission",
    "require_permission",
    "require_function_permission",
    "ROLE_PERMISSIONS",
    "FUNCTION_PERMISSIONS",
]
