"""
Permission and Role-Based Access Control (RBAC) system for GLaDOS.

This module provides:
- Permission definitions for tools and features
- Role-based permission management
- Permission checking for function calls and features

v2.1+: RBAC foundation for controlling access to tools and features
"""

from enum import Enum
from typing import Dict, List, Optional, Set

from pydantic import BaseModel


class Permission(str, Enum):
    """
    Enum of all permissions in GLaDOS.

    Each permission controls access to a specific tool or feature.
    """
    # Conversation and Memory
    CHAT = "chat"                           # Basic conversation access
    VIEW_MEMORY = "view_memory"             # View conversation history
    SEARCH_MEMORY = "search_memory"         # Search through memories

    # Calendar & Scheduling
    CREATE_CALENDAR_EVENT = "create_calendar_event"
    VIEW_CALENDAR_EVENTS = "view_calendar_events"
    EDIT_CALENDAR_EVENT = "edit_calendar_event"
    DELETE_CALENDAR_EVENT = "delete_calendar_event"

    # Reminders
    CREATE_REMINDER = "create_reminder"
    VIEW_REMINDERS = "view_reminders"
    EDIT_REMINDER = "edit_reminder"
    DELETE_REMINDER = "delete_reminder"

    # Todo Management
    CREATE_TODO = "create_todo"
    VIEW_TODOS = "view_todos"
    EDIT_TODO = "edit_todo"
    DELETE_TODO = "delete_todo"

    # Time & Information
    GET_TIME = "get_time"
    GET_WEATHER = "get_weather"

    # Admin Functions
    MANAGE_USERS = "manage_users"           # Create/modify/delete users
    MANAGE_ROLES = "manage_roles"           # Create/modify roles
    VIEW_LOGS = "view_logs"                 # View system logs
    REVOKE_TOKENS = "revoke_tokens"         # Revoke authentication tokens


class Role(str, Enum):
    """
    Predefined roles with different permission levels.
    """
    ADMIN = "admin"             # Full access to all features
    USER = "user"               # Standard user with most features
    GUEST = "guest"             # Limited access, read-only features
    RESTRICTED = "restricted"   # Very limited access, basic chat only


# Map each role to its permissions
ROLE_PERMISSIONS: Dict[Role, Set[Permission]] = {
    Role.ADMIN: {
        # All permissions for admin
        Permission.CHAT,
        Permission.VIEW_MEMORY,
        Permission.SEARCH_MEMORY,
        Permission.CREATE_CALENDAR_EVENT,
        Permission.VIEW_CALENDAR_EVENTS,
        Permission.EDIT_CALENDAR_EVENT,
        Permission.DELETE_CALENDAR_EVENT,
        Permission.CREATE_REMINDER,
        Permission.VIEW_REMINDERS,
        Permission.EDIT_REMINDER,
        Permission.DELETE_REMINDER,
        Permission.CREATE_TODO,
        Permission.VIEW_TODOS,
        Permission.EDIT_TODO,
        Permission.DELETE_TODO,
        Permission.GET_TIME,
        Permission.GET_WEATHER,
        Permission.MANAGE_USERS,
        Permission.MANAGE_ROLES,
        Permission.VIEW_LOGS,
        Permission.REVOKE_TOKENS,
    },

    Role.USER: {
        # Standard user permissions (no admin functions)
        Permission.CHAT,
        Permission.VIEW_MEMORY,
        Permission.SEARCH_MEMORY,
        Permission.CREATE_CALENDAR_EVENT,
        Permission.VIEW_CALENDAR_EVENTS,
        Permission.EDIT_CALENDAR_EVENT,
        Permission.DELETE_CALENDAR_EVENT,
        Permission.CREATE_REMINDER,
        Permission.VIEW_REMINDERS,
        Permission.EDIT_REMINDER,
        Permission.DELETE_REMINDER,
        Permission.CREATE_TODO,
        Permission.VIEW_TODOS,
        Permission.EDIT_TODO,
        Permission.DELETE_TODO,
        Permission.GET_TIME,
        Permission.GET_WEATHER,
    },

    Role.GUEST: {
        # Guest permissions (read-only)
        Permission.CHAT,
        Permission.VIEW_MEMORY,
        Permission.VIEW_CALENDAR_EVENTS,
        Permission.VIEW_REMINDERS,
        Permission.VIEW_TODOS,
        Permission.GET_TIME,
        Permission.GET_WEATHER,
    },

    Role.RESTRICTED: {
        # Very limited permissions
        Permission.CHAT,
        Permission.GET_TIME,
    },
}


# Map function names to required permissions
FUNCTION_PERMISSIONS: Dict[str, Permission] = {
    # Memory functions
    "search_memories": Permission.SEARCH_MEMORY,

    # Calendar functions
    "create_calendar_event": Permission.CREATE_CALENDAR_EVENT,
    "list_calendar_events": Permission.VIEW_CALENDAR_EVENTS,

    # Reminder functions
    "create_reminder": Permission.CREATE_REMINDER,
    "list_reminders": Permission.VIEW_REMINDERS,

    # Todo functions
    "create_todo": Permission.CREATE_TODO,
    "list_todos": Permission.VIEW_TODOS,

    # Information functions
    "get_current_time": Permission.GET_TIME,
    "get_weather": Permission.GET_WEATHER,
}


class PermissionChecker:
    """
    Checks if a user has permission to perform an action.

    This class provides methods to verify permissions based on user roles.
    """

    def __init__(self):
        """Initialize permission checker."""
        self.role_permissions = ROLE_PERMISSIONS
        self.function_permissions = FUNCTION_PERMISSIONS

    def has_permission(self, user_role: str, permission: Permission) -> bool:
        """
        Check if a user role has a specific permission.

        Args:
            user_role: The user's role (from User.role)
            permission: The permission to check

        Returns:
            bool: True if the role has the permission, False otherwise
        """
        try:
            role_enum = Role(user_role)
            return permission in self.role_permissions.get(role_enum, set())
        except ValueError:
            # Unknown role, no permissions
            return False

    def can_call_function(self, user_role: str, function_name: str) -> bool:
        """
        Check if a user role can call a specific function.

        Args:
            user_role: The user's role (from User.role)
            function_name: The name of the function to call

        Returns:
            bool: True if the role can call the function, False otherwise
        """
        # If function doesn't require specific permission, allow it
        if function_name not in self.function_permissions:
            return True

        required_permission = self.function_permissions[function_name]
        return self.has_permission(user_role, required_permission)

    def get_role_permissions(self, user_role: str) -> Set[Permission]:
        """
        Get all permissions for a role.

        Args:
            user_role: The user's role

        Returns:
            Set[Permission]: Set of all permissions for the role
        """
        try:
            role_enum = Role(user_role)
            return self.role_permissions.get(role_enum, set())
        except ValueError:
            return set()

    def get_allowed_functions(self, user_role: str) -> List[str]:
        """
        Get list of all functions the user role can call.

        Args:
            user_role: The user's role

        Returns:
            List[str]: List of function names the role can call
        """
        allowed = []
        for func_name, required_perm in self.function_permissions.items():
            if self.has_permission(user_role, required_perm):
                allowed.append(func_name)
        return allowed


class PermissionDeniedError(Exception):
    """
    Raised when a user attempts an action they don't have permission for.

    Attributes:
        user_id: The user who was denied
        action: The action that was denied
        required_permission: The permission that was required
    """

    def __init__(
        self,
        user_id: str,
        action: str,
        required_permission: Optional[Permission] = None,
    ):
        self.user_id = user_id
        self.action = action
        self.required_permission = required_permission

        message = f"User {user_id} denied permission for action: {action}"
        if required_permission:
            message += f" (requires: {required_permission.value})"

        super().__init__(message)


# Global permission checker instance
_permission_checker = PermissionChecker()


def check_permission(user_role: str, permission: Permission) -> bool:
    """
    Global helper to check if a user role has a permission.

    Args:
        user_role: The user's role
        permission: The permission to check

    Returns:
        bool: True if authorized, False otherwise
    """
    return _permission_checker.has_permission(user_role, permission)


def check_function_permission(user_role: str, function_name: str) -> bool:
    """
    Global helper to check if a user role can call a function.

    Args:
        user_role: The user's role
        function_name: The function to check

    Returns:
        bool: True if authorized, False otherwise
    """
    return _permission_checker.can_call_function(user_role, function_name)


def require_permission(user_id: str, user_role: str, permission: Permission) -> None:
    """
    Require a permission, raising PermissionDeniedError if not authorized.

    Args:
        user_id: The user's ID
        user_role: The user's role
        permission: The required permission

    Raises:
        PermissionDeniedError: If the user doesn't have the permission
    """
    if not check_permission(user_role, permission):
        raise PermissionDeniedError(
            user_id=user_id,
            action=permission.value,
            required_permission=permission,
        )


def require_function_permission(
    user_id: str,
    user_role: str,
    function_name: str,
) -> None:
    """
    Require permission to call a function, raising error if not authorized.

    Args:
        user_id: The user's ID
        user_role: The user's role
        function_name: The function to call

    Raises:
        PermissionDeniedError: If the user doesn't have permission
    """
    if not check_function_permission(user_role, function_name):
        required_perm = _permission_checker.function_permissions.get(function_name)
        raise PermissionDeniedError(
            user_id=user_id,
            action=f"call function '{function_name}'",
            required_permission=required_perm,
        )
