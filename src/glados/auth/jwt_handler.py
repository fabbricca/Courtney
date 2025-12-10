"""
JWT token generation and validation.

Handles creation and verification of JWT tokens for authentication.
"""

import secrets
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional
from dataclasses import dataclass

try:
    import jwt
except ImportError:
    jwt = None

from loguru import logger


# Configuration - should be loaded from environment in production
SECRET_KEY = secrets.token_urlsafe(64)  # Generate once, store securely
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60  # 1 hour
REFRESH_TOKEN_EXPIRE_DAYS = 30  # 30 days


@dataclass
class TokenPayload:
    """
    Decoded JWT payload.

    Attributes:
        user_id: User UUID
        username: Username
        email: User email
        roles: List of role names
        permissions: List of permission names
        exp: Expiration timestamp
        iat: Issued at timestamp
        jti: JWT ID for revocation
        token_type: Token type ("access" or "refresh")
    """
    user_id: str
    username: str
    email: str
    roles: List[str]
    permissions: List[str]
    exp: datetime
    iat: datetime
    jti: str
    token_type: str


class JWTHandler:
    """
    JWT token handler.

    Creates and validates JWT tokens for authentication.
    """

    def __init__(self, secret_key: str = SECRET_KEY, algorithm: str = ALGORITHM):
        """
        Initialize handler.

        Args:
            secret_key: Secret key for signing tokens
            algorithm: JWT algorithm (default: HS256)
        """
        if jwt is None:
            raise ImportError("pyjwt not installed. Run: pip install pyjwt")

        self.secret_key = secret_key
        self.algorithm = algorithm

    def create_access_token(
        self,
        user_id: str,
        username: str,
        email: str,
        roles: List[str],
        permissions: List[str]
    ) -> str:
        """
        Create JWT access token.

        Args:
            user_id: User UUID
            username: Username
            email: User email
            roles: List of role names
            permissions: List of permission names

        Returns:
            JWT token string
        """
        now = datetime.now(timezone.utc)
        expire = now + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)

        payload = {
            "iat": now.timestamp(),
            "exp": expire.timestamp(),
            "sub": user_id,  # Subject (standard JWT claim)
            "user_id": user_id,
            "username": username,
            "email": email,
            "roles": roles,
            "permissions": permissions,
            "jti": secrets.token_urlsafe(16),  # JWT ID for revocation
            "type": "access"
        }

        token = jwt.encode(payload, self.secret_key, algorithm=self.algorithm)
        logger.debug(f"Access token created for user {username}")

        return token

    def create_refresh_token(self, user_id: str, username: str) -> str:
        """
        Create refresh token (long-lived).

        Args:
            user_id: User UUID
            username: Username

        Returns:
            JWT refresh token string
        """
        now = datetime.now(timezone.utc)
        expire = now + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)

        payload = {
            "iat": now.timestamp(),
            "exp": expire.timestamp(),
            "sub": user_id,
            "username": username,
            "jti": secrets.token_urlsafe(16),
            "type": "refresh"
        }

        token = jwt.encode(payload, self.secret_key, algorithm=self.algorithm)
        return token

    def verify_token(self, token: str) -> Optional[TokenPayload]:
        """
        Verify and decode JWT token.

        Args:
            token: JWT token string

        Returns:
            TokenPayload if valid, None if invalid
        """
        try:
            payload = jwt.decode(
                token,
                self.secret_key,
                algorithms=[self.algorithm]
            )

            # Verify token type
            if payload.get("type") != "access":
                logger.warning("Token is not an access token")
                return None

            return TokenPayload(
                user_id=payload["user_id"],
                username=payload["username"],
                email=payload["email"],
                roles=payload.get("roles", []),
                permissions=payload.get("permissions", []),
                exp=datetime.fromtimestamp(payload["exp"], tz=timezone.utc),
                iat=datetime.fromtimestamp(payload["iat"], tz=timezone.utc),
                jti=payload["jti"],
                token_type=payload["type"]
            )

        except jwt.ExpiredSignatureError:
            logger.warning("Token has expired")
            return None
        except jwt.InvalidTokenError as e:
            logger.warning(f"Invalid token: {e}")
            return None

    def decode_without_verification(self, token: str) -> Optional[Dict]:
        """
        Decode token without verifying (for inspection only).

        Args:
            token: JWT token string

        Returns:
            Decoded payload dict, or None on error

        Warning:
            This method does NOT verify the token signature.
            Only use for debugging/inspection purposes.
        """
        try:
            return jwt.decode(token, options={"verify_signature": False})
        except Exception as e:
            logger.error(f"Failed to decode token: {e}")
            return None

    def extract_jti(self, token: str) -> Optional[str]:
        """
        Extract JWT ID from token without full verification.

        Args:
            token: JWT token string

        Returns:
            JWT ID (jti claim) or None
        """
        payload = self.decode_without_verification(token)
        if payload:
            return payload.get("jti")
        return None
