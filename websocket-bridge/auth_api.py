"""
Authentication API for WebSocket Bridge
Handles login requests and returns JWT tokens - standalone version
"""

import sqlite3
import bcrypt
import jwt
import uuid
from datetime import datetime, timedelta
from pathlib import Path
import logging
from aiohttp import web

logger = logging.getLogger('auth_api')

# Paths
PROJECT_ROOT = Path(__file__).parent.parent
DB_PATH = PROJECT_ROOT / "data" / "users.db"
JWT_SECRET_FILE = PROJECT_ROOT / "data" / ".jwt_secret"

# JWT Configuration
JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=24)
JWT_REFRESH_TOKEN_EXPIRES = timedelta(days=30)


def load_jwt_secret():
    """Load JWT secret from file."""
    try:
        if JWT_SECRET_FILE.exists():
            return JWT_SECRET_FILE.read_text().strip()
        else:
            logger.error(f"JWT secret file not found: {JWT_SECRET_FILE}")
            return None
    except Exception as e:
        logger.error(f"Failed to load JWT secret: {e}")
        return None


def create_jwt_token(user_id, username, secret, expires_delta):
    """Create a JWT token."""
    jti = str(uuid.uuid4())
    now = datetime.utcnow()
    expires_at = now + expires_delta

    payload = {
        'user_id': user_id,
        'sub': username,
        'jti': jti,
        'iat': now.timestamp(),
        'exp': expires_at.timestamp()
    }

    token = jwt.encode(payload, secret, algorithm='HS256')

    return {
        'token': token,
        'jti': jti,
        'expires_at': expires_at.isoformat()
    }


def verify_jwt_token(token, secret):
    """Verify and decode a JWT token."""
    try:
        payload = jwt.decode(token, secret, algorithms=['HS256'])
        return payload
    except jwt.ExpiredSignatureError:
        logger.warning("Token expired")
        return None
    except jwt.InvalidTokenError as e:
        logger.warning(f"Invalid token: {e}")
        return None


async def handle_login(request):
    """
    Handle login request.

    POST /api/login
    Body: {"username": "...", "password": "..."}
    Returns: {"success": true, "token": "...", "user": {...}}
    """
    try:
        # Parse request body
        data = await request.json()
        username = data.get('username', '').strip()
        password = data.get('password', '')

        if not username or not password:
            return web.json_response({
                'success': False,
                'error': 'Username and password required'
            }, status=400)

        # Load JWT secret
        jwt_secret = load_jwt_secret()
        if not jwt_secret:
            return web.json_response({
                'success': False,
                'error': 'Server configuration error'
            }, status=500)

        # Connect to database
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Get user by username
        cursor.execute("""
            SELECT user_id, username, email, password_hash, role,
                   is_admin, is_active, created_at
            FROM users
            WHERE username = ?
        """, (username,))

        user = cursor.fetchone()

        if not user:
            # User not found
            logger.warning(f"Login attempt for non-existent user: {username}")
            conn.close()
            return web.json_response({
                'success': False,
                'error': 'Invalid username or password'
            }, status=401)

        # Check if user is active
        if not user['is_active']:
            logger.warning(f"Login attempt for inactive user: {username}")
            conn.close()
            return web.json_response({
                'success': False,
                'error': 'Account is disabled'
            }, status=403)

        # Verify password
        if not bcrypt.checkpw(password.encode('utf-8'), user['password_hash'].encode('utf-8')):
            logger.warning(f"Failed login attempt for user: {username}")
            conn.close()
            return web.json_response({
                'success': False,
                'error': 'Invalid username or password'
            }, status=401)

        # Generate JWT tokens
        access_token = create_jwt_token(
            user['user_id'],
            user['username'],
            jwt_secret,
            JWT_ACCESS_TOKEN_EXPIRES
        )

        refresh_token = create_jwt_token(
            user['user_id'],
            user['username'],
            jwt_secret,
            JWT_REFRESH_TOKEN_EXPIRES
        )

        # Create session in database
        cursor.execute("""
            INSERT INTO sessions (user_id, jti, refresh_token_jti, created_at, last_activity)
            VALUES (?, ?, ?, ?, ?)
        """, (
            user['user_id'],
            access_token['jti'],
            refresh_token['jti'],
            datetime.utcnow().isoformat(),
            datetime.utcnow().isoformat()
        ))

        conn.commit()
        conn.close()

        logger.info(f"Successful login for user: {username} (role: {user['role']})")

        return web.json_response({
            'success': True,
            'token': access_token['token'],
            'refresh_token': refresh_token['token'],
            'user': {
                'user_id': user['user_id'],
                'username': user['username'],
                'email': user['email'],
                'role': user['role'],
                'is_admin': bool(user['is_admin'])
            }
        })

    except Exception as e:
        logger.error(f"Login error: {e}", exc_info=True)
        return web.json_response({
            'success': False,
            'error': 'Internal server error'
        }, status=500)


async def handle_logout(request):
    """
    Handle logout request.

    POST /api/logout
    Headers: Authorization: Bearer <token>
    Returns: {"success": true}
    """
    try:
        # Get token from Authorization header
        auth_header = request.headers.get('Authorization', '')
        if not auth_header.startswith('Bearer '):
            return web.json_response({
                'success': False,
                'error': 'No token provided'
            }, status=401)

        token = auth_header[7:]  # Remove 'Bearer ' prefix

        # Load JWT secret
        jwt_secret = load_jwt_secret()
        if not jwt_secret:
            return web.json_response({
                'success': False,
                'error': 'Server configuration error'
            }, status=500)

        # Verify and decode token
        payload = verify_jwt_token(token, jwt_secret)

        if not payload:
            return web.json_response({
                'success': False,
                'error': 'Invalid token'
            }, status=401)

        # Delete session from database
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        jti = payload.get('jti')
        if jti:
            cursor.execute("DELETE FROM sessions WHERE jti = ?", (jti,))
            conn.commit()

        conn.close()

        logger.info(f"User logged out: {payload.get('sub')}")

        return web.json_response({
            'success': True
        })

    except Exception as e:
        logger.error(f"Logout error: {e}", exc_info=True)
        return web.json_response({
            'success': False,
            'error': 'Internal server error'
        }, status=500)


# CORS middleware
@web.middleware
async def cors_middleware(request, handler):
    """Add CORS headers to all responses."""
    if request.method == 'OPTIONS':
        # Preflight request
        response = web.Response()
    else:
        response = await handler(request)

    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
    return response
