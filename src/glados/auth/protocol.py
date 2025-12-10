"""
Authentication protocol for network connections.

Defines protocol markers and provides middleware for JWT authentication
on socket connections.
"""

import struct
import socket
from typing import Optional, Tuple
from dataclasses import dataclass

from loguru import logger
from .jwt_handler import TokenPayload
from .user_manager import UserManager


# Authentication protocol markers (added to existing network protocol)
AUTH_REQUEST = 0xFFFFFFFB              # Client sends JWT token
AUTH_RESPONSE_SUCCESS = 0xFFFFFFFA     # Server: auth succeeded
AUTH_RESPONSE_FAILURE = 0xFFFFFFF9     # Server: auth failed


@dataclass
class ConnectionContext:
    """
    Connection context after successful authentication.

    Contains user information and permissions for the connection.
    """
    user_id: str
    username: str
    email: str
    roles: list[str]
    permissions: list[str]
    is_admin: bool


class AuthenticationMiddleware:
    """
    Authentication middleware for socket connections.

    Handles JWT authentication handshake before allowing normal protocol.
    """

    def __init__(
        self,
        user_manager: Optional[UserManager] = None,
        require_auth: bool = True,
        timeout: float = 10.0
    ):
        """
        Initialize authentication middleware.

        Args:
            user_manager: UserManager instance for token verification
            require_auth: If False, allow connections without auth (backward compat)
            timeout: Timeout for auth handshake in seconds
        """
        self.user_manager = user_manager
        self.require_auth = require_auth
        self.timeout = timeout

    def authenticate_connection(
        self,
        client_socket: socket.socket
    ) -> Optional[ConnectionContext]:
        """
        Perform authentication handshake with client.

        Protocol:
            Client → Server: [AUTH_REQUEST][token_length][jwt_bytes]
            Server → Client: [AUTH_RESPONSE_SUCCESS][user_id_length][user_id_bytes]
                         or: [AUTH_RESPONSE_FAILURE][error_length][error_message]

        Args:
            client_socket: Connected client socket

        Returns:
            ConnectionContext if authentication succeeds, None if it fails
        """
        if not self.require_auth:
            # Authentication disabled - create default context
            logger.info("Authentication disabled, allowing connection")
            return ConnectionContext(
                user_id="default",
                username="default_user",
                email="default@localhost",
                roles=["user"],
                permissions=["*:*"],  # All permissions
                is_admin=True
            )

        if not self.user_manager:
            logger.error("Authentication required but no UserManager provided")
            self._send_auth_failure(client_socket, "Server misconfiguration")
            return None

        # Set timeout for auth handshake
        original_timeout = client_socket.gettimeout()
        client_socket.settimeout(self.timeout)

        try:
            # Wait for AUTH_REQUEST header (8 bytes: marker + length)
            header_data = self._recv_exact(client_socket, 8)
            if not header_data:
                logger.warning("Client disconnected during auth handshake")
                return None

            marker, token_length = struct.unpack("<II", header_data)

            if marker != AUTH_REQUEST:
                logger.warning(f"Expected AUTH_REQUEST (0x{AUTH_REQUEST:08X}), got 0x{marker:08X}")
                self._send_auth_failure(client_socket, "Invalid auth request")
                return None

            # Receive JWT token
            if token_length > 10000:  # Sanity check (JWTs are typically < 2KB)
                logger.warning(f"Token too large: {token_length} bytes")
                self._send_auth_failure(client_socket, "Token too large")
                return None

            token_bytes = self._recv_exact(client_socket, token_length)
            if not token_bytes:
                logger.warning("Failed to receive token data")
                return None

            token = token_bytes.decode('utf-8', errors='replace')
            logger.debug(f"Received JWT token ({len(token)} chars)")

            # Verify token
            payload = self.user_manager.verify_token(token)
            if not payload:
                logger.warning("Invalid or expired token")
                self._send_auth_failure(client_socket, "Invalid or expired token")
                return None

            # Check if user is active
            user = self.user_manager.db.get_user_by_id(payload.user_id)
            if not user or not user.is_active:
                logger.warning(f"User {payload.username} is not active")
                self._send_auth_failure(client_socket, "User account inactive")
                return None

            # Authentication successful!
            logger.success(f"User authenticated: {payload.username} ({payload.user_id})")

            # Send success response
            user_id_bytes = payload.user_id.encode('utf-8')
            success_header = struct.pack("<II", AUTH_RESPONSE_SUCCESS, len(user_id_bytes))
            client_socket.sendall(success_header + user_id_bytes)

            # Create connection context
            context = ConnectionContext(
                user_id=payload.user_id,
                username=payload.username,
                email=payload.email,
                roles=payload.roles,
                permissions=payload.permissions,
                is_admin="admin" in payload.roles
            )

            return context

        except socket.timeout:
            logger.warning("Auth handshake timed out")
            self._send_auth_failure(client_socket, "Authentication timeout")
            return None
        except Exception as e:
            logger.error(f"Auth handshake error: {e}")
            self._send_auth_failure(client_socket, "Authentication error")
            return None
        finally:
            # Restore original timeout
            client_socket.settimeout(original_timeout)

    def _recv_exact(self, sock: socket.socket, n: int) -> Optional[bytes]:
        """
        Receive exactly n bytes from socket.

        Args:
            sock: Socket to receive from
            n: Number of bytes to receive

        Returns:
            Bytes received, or None on error
        """
        data = b""
        while len(data) < n:
            try:
                chunk = sock.recv(n - len(data))
                if not chunk:
                    return None
                data += chunk
            except Exception as e:
                logger.error(f"Error receiving data: {e}")
                return None
        return data

    def _send_auth_failure(self, sock: socket.socket, message: str) -> None:
        """
        Send authentication failure response.

        Args:
            sock: Socket to send to
            message: Error message
        """
        try:
            error_bytes = message.encode('utf-8')
            header = struct.pack("<II", AUTH_RESPONSE_FAILURE, len(error_bytes))
            sock.sendall(header + error_bytes)
        except Exception as e:
            logger.error(f"Failed to send auth failure: {e}")


def has_permission(context: ConnectionContext, permission: str) -> bool:
    """
    Check if connection has specific permission.

    Args:
        context: Connection context
        permission: Permission name (e.g., "tool:web_search")

    Returns:
        True if connection has permission
    """
    # Admin has all permissions
    if context.is_admin or "*:*" in context.permissions:
        return True

    # Check exact match
    if permission in context.permissions:
        return True

    # Check wildcard (e.g., "tool:*" matches "tool:web_search")
    for perm in context.permissions:
        if perm.endswith(":*"):
            prefix = perm[:-2]
            if permission.startswith(prefix + ":"):
                return True

    return False
