#!/usr/bin/env python3
"""
Client-side authentication helper.

Handles JWT token storage, login, and authentication handshake with server.
"""

import socket
import struct
from pathlib import Path
from typing import Optional, Tuple
import json
import getpass

from loguru import logger

# Protocol markers (must match server)
AUTH_REQUEST = 0xFFFFFFFB
AUTH_RESPONSE_SUCCESS = 0xFFFFFFFA
AUTH_RESPONSE_FAILURE = 0xFFFFFFF9


class ClientAuthHelper:
    """
    Client-side authentication helper.

    Manages JWT tokens and performs authentication handshake with server.
    """

    def __init__(self, token_file: Optional[Path] = None):
        """
        Initialize auth helper.

        Args:
            token_file: Path to file storing JWT token (default: ~/.glados_token)
        """
        if token_file is None:
            token_file = Path.home() / ".glados_token"

        self.token_file = token_file
        self._token: Optional[str] = None

    def load_token(self) -> Optional[str]:
        """
        Load JWT token from file.

        Returns:
            JWT token string, or None if file doesn't exist
        """
        if not self.token_file.exists():
            return None

        try:
            with open(self.token_file, 'r') as f:
                data = json.load(f)
                self._token = data.get('access_token')
                return self._token
        except Exception as e:
            logger.error(f"Failed to load token: {e}")
            return None

    def save_token(self, access_token: str, refresh_token: Optional[str] = None) -> bool:
        """
        Save JWT tokens to file.

        Args:
            access_token: Access token
            refresh_token: Refresh token (optional)

        Returns:
            True if saved successfully
        """
        try:
            data = {
                'access_token': access_token
            }
            if refresh_token:
                data['refresh_token'] = refresh_token

            # Create parent directory if needed
            self.token_file.parent.mkdir(parents=True, exist_ok=True)

            # Save with restricted permissions (600)
            with open(self.token_file, 'w') as f:
                json.dump(data, f, indent=2)

            self.token_file.chmod(0o600)  # rw-------
            self._token = access_token

            logger.info(f"Token saved to {self.token_file}")
            return True

        except Exception as e:
            logger.error(f"Failed to save token: {e}")
            return False

    def clear_token(self):
        """Remove stored token."""
        self._token = None
        if self.token_file.exists():
            try:
                self.token_file.unlink()
                logger.info("Token cleared")
            except Exception as e:
                logger.error(f"Failed to clear token: {e}")

    def get_token(self) -> Optional[str]:
        """
        Get current token (load from file if not in memory).

        Returns:
            JWT token or None
        """
        if self._token is None:
            self._token = self.load_token()
        return self._token

    def authenticate_connection(self, sock: socket.socket, token: Optional[str] = None) -> bool:
        """
        Perform authentication handshake with server.

        Protocol:
            Client → Server: [AUTH_REQUEST][token_length][jwt_bytes]
            Server → Client: [AUTH_RESPONSE_SUCCESS][user_id] or [AUTH_RESPONSE_FAILURE][error]

        Args:
            sock: Connected socket
            token: JWT token (if None, will try to load from file)

        Returns:
            True if authentication succeeded, False otherwise
        """
        if token is None:
            token = self.get_token()

        if not token:
            logger.error("No authentication token available")
            return False

        try:
            # Send AUTH_REQUEST
            token_bytes = token.encode('utf-8')
            header = struct.pack("<II", AUTH_REQUEST, len(token_bytes))
            sock.sendall(header + token_bytes)

            logger.debug(f"Sent auth request ({len(token)} chars)")

            # Wait for response (8 bytes header)
            response_header = self._recv_exact(sock, 8)
            if not response_header:
                logger.error("No auth response from server")
                return False

            marker, data_length = struct.unpack("<II", response_header)

            if marker == AUTH_RESPONSE_SUCCESS:
                # Success! Receive user_id
                user_id_bytes = self._recv_exact(sock, data_length)
                if user_id_bytes:
                    user_id = user_id_bytes.decode('utf-8', errors='replace')
                    logger.success(f"Authentication successful! User ID: {user_id}")
                    return True
                else:
                    logger.error("Failed to receive user ID")
                    return False

            elif marker == AUTH_RESPONSE_FAILURE:
                # Authentication failed
                error_bytes = self._recv_exact(sock, data_length)
                if error_bytes:
                    error_msg = error_bytes.decode('utf-8', errors='replace')
                    logger.error(f"Authentication failed: {error_msg}")
                else:
                    logger.error("Authentication failed (no error message)")
                return False

            else:
                logger.error(f"Unexpected auth response marker: 0x{marker:08X}")
                return False

        except Exception as e:
            logger.error(f"Authentication handshake error: {e}")
            return False

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


def interactive_login(server_url: str) -> Optional[Tuple[str, str]]:
    """
    Interactive login flow (for use in scripts/CLIs).

    Args:
        server_url: Server URL (host:port)

    Returns:
        (access_token, refresh_token) if successful, None otherwise

    Note:
        This requires the server to have a login endpoint.
        For now, this is a placeholder for future implementation.
    """
    print(f"Logging in to {server_url}...")
    print()

    username = input("Username: ").strip()
    if not username:
        print("Error: Username required")
        return None

    password = getpass.getpass("Password: ")
    if not password:
        print("Error: Password required")
        return None

    # TODO: Implement HTTP login endpoint on server
    # For now, this is a placeholder
    print()
    print("Error: Direct login not yet implemented")
    print("Please use the admin script to create a user and generate tokens")
    print()
    return None
