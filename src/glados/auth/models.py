"""
User authentication data models.

Data classes for users, roles, permissions, and sessions.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class User:
    """
    User account.

    Attributes:
        user_id: Unique user identifier (UUID)
        username: Unique username
        email: User email address
        password_hash: Bcrypt hashed password
        created_at: Account creation timestamp
        is_active: Whether account is active
        is_admin: Whether user has admin privileges
    """
    user_id: str
    username: str
    email: str
    password_hash: str
    created_at: datetime
    is_active: bool = True
    is_admin: bool = False


@dataclass
class Role:
    """
    User role for RBAC.

    Attributes:
        role_id: Unique role identifier
        name: Role name (e.g., "admin", "user", "developer")
        description: Human-readable description
    """
    role_id: str
    name: str
    description: str


@dataclass
class Permission:
    """
    Permission for tool/feature access.

    Attributes:
        permission_id: Unique permission identifier
        name: Permission name (e.g., "tool:web_search")
        description: Human-readable description
        resource: Resource identifier (e.g., "tool:web_search", "memory:write")
    """
    permission_id: str
    name: str
    description: str
    resource: str


@dataclass
class Session:
    """
    Active user session.

    Attributes:
        session_id: Unique session identifier
        user_id: User who owns this session
        token_jti: JWT ID (jti claim) for token revocation
        created_at: Session creation timestamp
        expires_at: Session expiration timestamp
        last_activity: Last activity timestamp
        ip_address: Client IP address (optional)
    """
    session_id: str
    user_id: str
    token_jti: str
    created_at: datetime
    expires_at: datetime
    last_activity: datetime
    ip_address: Optional[str] = None
