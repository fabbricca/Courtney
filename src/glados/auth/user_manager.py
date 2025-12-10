"""
User authentication manager.

Combines user database and JWT handling for complete authentication flow.
"""

from typing import Optional, Tuple
from pathlib import Path

from loguru import logger
from .database import UserDatabase
from .jwt_handler import JWTHandler, TokenPayload


class UserManager:
    """
    User authentication and authorization manager.

    Combines user database and JWT handling to provide:
    - User login/logout
    - Token generation and verification
    - Permission checking
    """

    def __init__(self, db_path: Path, secret_key: str):
        """
        Initialize manager.

        Args:
            db_path: Path to user database
            secret_key: Secret key for JWT signing
        """
        self.db = UserDatabase(db_path)
        self.jwt = JWTHandler(secret_key)

    def login(self, username: str, password: str) -> Optional[Tuple[str, str]]:
        """
        Authenticate user and return tokens.

        Args:
            username: Username
            password: Plain text password

        Returns:
            (access_token, refresh_token) tuple if successful, None otherwise
        """
        # Get user
        user = self.db.get_user_by_username(username)
        if not user:
            logger.warning(f"Login failed: user '{username}' not found")
            return None

        # Check if active
        if not user.is_active:
            logger.warning(f"Login failed: user '{username}' is inactive")
            return None

        # Verify password
        if not self.db.verify_password(user, password):
            logger.warning(f"Login failed: invalid password for '{username}'")
            return None

        # Get permissions and roles
        permissions = self.db.get_user_permissions(user.user_id)
        roles = self.db.get_user_roles(user.user_id)

        # Add admin permission if admin user
        if user.is_admin:
            if "admin" not in roles:
                roles.append("admin")
            if "admin:*" not in permissions:
                permissions.append("admin:*")

        # Create tokens
        access_token = self.jwt.create_access_token(
            user_id=user.user_id,
            username=user.username,
            email=user.email,
            roles=roles,
            permissions=permissions
        )

        refresh_token = self.jwt.create_refresh_token(
            user_id=user.user_id,
            username=user.username
        )

        logger.info(f"User logged in: {username}")
        return (access_token, refresh_token)

    def verify_token(self, token: str) -> Optional[TokenPayload]:
        """
        Verify JWT token.

        Args:
            token: JWT token string

        Returns:
            TokenPayload if valid, None if invalid
        """
        return self.jwt.verify_token(token)

    def has_permission(self, token_payload: TokenPayload, permission: str) -> bool:
        """
        Check if user has specific permission.

        Args:
            token_payload: Decoded token
            permission: Permission name (e.g., "tool:web_search")

        Returns:
            True if user has permission

        Examples:
            >>> has_permission(payload, "chat:send")
            True
            >>> has_permission(payload, "tool:code_execution")
            False
        """
        # Admin has all permissions
        if "admin:*" in token_payload.permissions:
            return True

        # Check exact match
        if permission in token_payload.permissions:
            return True

        # Check wildcard (e.g., "tool:*" matches "tool:web_search")
        for perm in token_payload.permissions:
            if perm.endswith(":*"):
                prefix = perm[:-2]
                if permission.startswith(prefix + ":"):
                    return True

        return False

    def refresh_access_token(self, refresh_token: str) -> Optional[str]:
        """
        Create new access token from refresh token.

        Args:
            refresh_token: Valid refresh token

        Returns:
            New access token if valid, None otherwise
        """
        try:
            # Decode refresh token (without full verification)
            payload = self.jwt.decode_without_verification(refresh_token)
            if not payload or payload.get("type") != "refresh":
                logger.warning("Invalid refresh token type")
                return None

            # Get user
            user_id = payload.get("sub")
            user = self.db.get_user_by_id(user_id)
            if not user or not user.is_active:
                logger.warning("User not found or inactive")
                return None

            # Get fresh permissions and roles
            permissions = self.db.get_user_permissions(user.user_id)
            roles = self.db.get_user_roles(user.user_id)

            # Add admin permission if admin user
            if user.is_admin:
                if "admin" not in roles:
                    roles.append("admin")
                if "admin:*" not in permissions:
                    permissions.append("admin:*")

            # Create new access token
            access_token = self.jwt.create_access_token(
                user_id=user.user_id,
                username=user.username,
                email=user.email,
                roles=roles,
                permissions=permissions
            )

            logger.debug(f"Access token refreshed for user {user.username}")
            return access_token

        except Exception as e:
            logger.error(f"Failed to refresh token: {e}")
            return None

    def logout(self, token: str) -> bool:
        """
        Logout user by revoking token.

        Args:
            token: JWT access token

        Returns:
            True if logout succeeded
        """
        # Extract JWT ID
        jti = self.jwt.extract_jti(token)
        if not jti:
            return False

        # Delete session
        return self.db.delete_session(jti)
