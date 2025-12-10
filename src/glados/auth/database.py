"""
SQLite database for user management.

Thread-safe user database with support for users, roles, permissions, and sessions.
"""

import sqlite3
import threading
import uuid
from pathlib import Path
from typing import List, Optional
from datetime import datetime

try:
    import bcrypt
except ImportError:
    bcrypt = None

from loguru import logger
from .models import User, Role, Permission, Session


class UserDatabase:
    """
    Thread-safe user database.

    Manages users, roles, permissions, and sessions using SQLite.
    All operations are protected by threading.RLock for thread safety.
    """

    def __init__(self, db_path: Path):
        """
        Initialize database.

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path
        self._lock = threading.RLock()
        self._init_db()

    def _init_db(self):
        """Create tables if they don't exist."""
        with self._lock:
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()

            # Users table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id TEXT PRIMARY KEY,
                    username TEXT UNIQUE NOT NULL,
                    email TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    is_active INTEGER DEFAULT 1,
                    is_admin INTEGER DEFAULT 0,
                    role TEXT DEFAULT 'user'
                )
            """)

            # Migration: Add role column if it doesn't exist (v2.1+)
            try:
                cursor.execute("SELECT role FROM users LIMIT 1")
            except sqlite3.OperationalError:
                # Column doesn't exist, add it
                cursor.execute("ALTER TABLE users ADD COLUMN role TEXT DEFAULT 'user'")
                # Set admin role for existing admin users
                cursor.execute("UPDATE users SET role = 'admin' WHERE is_admin = 1")
                logger.info("Migrated database: Added role column to users table")

            # Roles table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS roles (
                    role_id TEXT PRIMARY KEY,
                    name TEXT UNIQUE NOT NULL,
                    description TEXT
                )
            """)

            # Permissions table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS permissions (
                    permission_id TEXT PRIMARY KEY,
                    name TEXT UNIQUE NOT NULL,
                    description TEXT,
                    resource TEXT NOT NULL
                )
            """)

            # User roles (many-to-many)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS user_roles (
                    user_id TEXT NOT NULL,
                    role_id TEXT NOT NULL,
                    assigned_at TEXT NOT NULL,
                    PRIMARY KEY (user_id, role_id),
                    FOREIGN KEY (user_id) REFERENCES users(user_id),
                    FOREIGN KEY (role_id) REFERENCES roles(role_id)
                )
            """)

            # Role permissions (many-to-many)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS role_permissions (
                    role_id TEXT NOT NULL,
                    permission_id TEXT NOT NULL,
                    PRIMARY KEY (role_id, permission_id),
                    FOREIGN KEY (role_id) REFERENCES roles(role_id),
                    FOREIGN KEY (permission_id) REFERENCES permissions(permission_id)
                )
            """)

            # Sessions table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    token_jti TEXT UNIQUE NOT NULL,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    last_activity TEXT NOT NULL,
                    ip_address TEXT,
                    FOREIGN KEY (user_id) REFERENCES users(user_id)
                )
            """)

            # Indexes for performance
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_sessions_jti ON sessions(token_jti)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_roles_user ON user_roles(user_id)")

            conn.commit()
            conn.close()

            logger.info(f"User database initialized: {self.db_path}")

    # ========================================================================
    # User Operations
    # ========================================================================

    def create_user(
        self,
        username: str,
        email: str,
        password: str,
        is_admin: bool = False,
        role: str = "user"
    ) -> User:
        """
        Create new user with hashed password.

        Args:
            username: Unique username
            email: User email
            password: Plain text password (will be hashed)
            is_admin: Whether user has admin privileges (deprecated, use role)
            role: User role for RBAC (admin/user/guest/restricted) (v2.1+)

        Returns:
            Created User object

        Raises:
            ValueError: If bcrypt is not installed
            sqlite3.IntegrityError: If username or email already exists
        """
        if bcrypt is None:
            raise ValueError("bcrypt not installed. Run: pip install bcrypt")

        with self._lock:
            # Hash password
            password_hash = bcrypt.hashpw(
                password.encode('utf-8'),
                bcrypt.gensalt()
            ).decode('utf-8')

            # If is_admin is True but role is default, set role to admin
            if is_admin and role == "user":
                role = "admin"

            user = User(
                user_id=str(uuid.uuid4()),
                username=username,
                email=email,
                password_hash=password_hash,
                created_at=datetime.now(),
                is_active=True,
                is_admin=is_admin,
                role=role
            )

            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()

            cursor.execute("""
                INSERT INTO users (user_id, username, email, password_hash, created_at, is_active, is_admin, role)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                user.user_id,
                user.username,
                user.email,
                user.password_hash,
                user.created_at.isoformat(),
                1 if user.is_active else 0,
                1 if user.is_admin else 0,
                user.role
            ))

            conn.commit()
            conn.close()

            logger.info(f"User created: {username} ({user.user_id}) with role: {role}")
            return user

    def get_user_by_username(self, username: str) -> Optional[User]:
        """
        Get user by username.

        Args:
            username: Username to search for

        Returns:
            User object if found, None otherwise
        """
        with self._lock:
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()

            cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
            row = cursor.fetchone()
            conn.close()

            if not row:
                return None

            return User(
                user_id=row[0],
                username=row[1],
                email=row[2],
                password_hash=row[3],
                created_at=datetime.fromisoformat(row[4]),
                is_active=bool(row[5]),
                is_admin=bool(row[6]),
                role=row[7] if len(row) > 7 else "user"  # v2.1+: RBAC role
            )

    def get_user_by_id(self, user_id: str) -> Optional[User]:
        """
        Get user by ID.

        Args:
            user_id: User ID to search for

        Returns:
            User object if found, None otherwise
        """
        with self._lock:
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()

            cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
            row = cursor.fetchone()
            conn.close()

            if not row:
                return None

            return User(
                user_id=row[0],
                username=row[1],
                email=row[2],
                password_hash=row[3],
                created_at=datetime.fromisoformat(row[4]),
                is_active=bool(row[5]),
                is_admin=bool(row[6]),
                role=row[7] if len(row) > 7 else "user"  # v2.1+: RBAC role
            )

    def verify_password(self, user: User, password: str) -> bool:
        """
        Verify password against user's hash.

        Args:
            user: User object
            password: Plain text password to verify

        Returns:
            True if password matches, False otherwise

        Raises:
            ValueError: If bcrypt is not installed
        """
        if bcrypt is None:
            raise ValueError("bcrypt not installed. Run: pip install bcrypt")

        return bcrypt.checkpw(
            password.encode('utf-8'),
            user.password_hash.encode('utf-8')
        )

    def list_users(self) -> List[User]:
        """
        Get all users.

        Returns:
            List of all User objects
        """
        with self._lock:
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()

            cursor.execute("SELECT * FROM users ORDER BY username")
            rows = cursor.fetchall()
            conn.close()

            users = []
            for row in rows:
                users.append(User(
                    user_id=row[0],
                    username=row[1],
                    email=row[2],
                    password_hash=row[3],
                    created_at=datetime.fromisoformat(row[4]),
                    is_active=bool(row[5]),
                    is_admin=bool(row[6])
                ))

            return users

    def update_user(self, user: User) -> bool:
        """
        Update user information.

        Args:
            user: User object with updated information

        Returns:
            True if update succeeded
        """
        with self._lock:
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()

            cursor.execute("""
                UPDATE users
                SET email = ?, is_active = ?, is_admin = ?
                WHERE user_id = ?
            """, (
                user.email,
                1 if user.is_active else 0,
                1 if user.is_admin else 0,
                user.user_id
            ))

            conn.commit()
            success = cursor.rowcount > 0
            conn.close()

            if success:
                logger.info(f"User updated: {user.username}")

            return success

    def delete_user(self, user_id: str) -> bool:
        """
        Delete user and all associated data.

        Args:
            user_id: User ID to delete

        Returns:
            True if deletion succeeded
        """
        with self._lock:
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()

            # Delete user roles
            cursor.execute("DELETE FROM user_roles WHERE user_id = ?", (user_id,))

            # Delete sessions
            cursor.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))

            # Delete user
            cursor.execute("DELETE FROM users WHERE user_id = ?", (user_id,))

            conn.commit()
            success = cursor.rowcount > 0
            conn.close()

            if success:
                logger.info(f"User deleted: {user_id}")

            return success

    # ========================================================================
    # Permission Operations
    # ========================================================================

    def get_user_permissions(self, user_id: str) -> List[str]:
        """
        Get all permissions for user (through roles).

        Args:
            user_id: User ID

        Returns:
            List of permission names (e.g., ["chat:send", "memory:read"])
        """
        with self._lock:
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()

            cursor.execute("""
                SELECT DISTINCT p.name
                FROM permissions p
                JOIN role_permissions rp ON p.permission_id = rp.permission_id
                JOIN user_roles ur ON rp.role_id = ur.role_id
                WHERE ur.user_id = ?
            """, (user_id,))

            permissions = [row[0] for row in cursor.fetchall()]
            conn.close()

            return permissions

    def get_user_roles(self, user_id: str) -> List[str]:
        """
        Get all roles for user.

        Args:
            user_id: User ID

        Returns:
            List of role names (e.g., ["user", "developer"])
        """
        with self._lock:
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()

            cursor.execute("""
                SELECT r.name
                FROM roles r
                JOIN user_roles ur ON r.role_id = ur.role_id
                WHERE ur.user_id = ?
            """, (user_id,))

            roles = [row[0] for row in cursor.fetchall()]
            conn.close()

            return roles

    # ========================================================================
    # Session Operations
    # ========================================================================

    def create_session(self, session: Session) -> bool:
        """
        Create new session.

        Args:
            session: Session object

        Returns:
            True if creation succeeded
        """
        with self._lock:
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()

            cursor.execute("""
                INSERT INTO sessions (session_id, user_id, token_jti, created_at, expires_at, last_activity, ip_address)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                session.session_id,
                session.user_id,
                session.token_jti,
                session.created_at.isoformat(),
                session.expires_at.isoformat(),
                session.last_activity.isoformat(),
                session.ip_address
            ))

            conn.commit()
            success = cursor.rowcount > 0
            conn.close()

            return success

    def get_session_by_jti(self, token_jti: str) -> Optional[Session]:
        """
        Get session by JWT ID.

        Args:
            token_jti: JWT ID (jti claim)

        Returns:
            Session object if found, None otherwise
        """
        with self._lock:
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()

            cursor.execute("SELECT * FROM sessions WHERE token_jti = ?", (token_jti,))
            row = cursor.fetchone()
            conn.close()

            if not row:
                return None

            return Session(
                session_id=row[0],
                user_id=row[1],
                token_jti=row[2],
                created_at=datetime.fromisoformat(row[3]),
                expires_at=datetime.fromisoformat(row[4]),
                last_activity=datetime.fromisoformat(row[5]),
                ip_address=row[6]
            )

    def delete_session(self, token_jti: str) -> bool:
        """
        Delete session (logout).

        Args:
            token_jti: JWT ID

        Returns:
            True if deletion succeeded
        """
        with self._lock:
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()

            cursor.execute("DELETE FROM sessions WHERE token_jti = ?", (token_jti,))

            conn.commit()
            success = cursor.rowcount > 0
            conn.close()

            return success

    def cleanup_expired_sessions(self) -> int:
        """
        Remove expired sessions.

        Returns:
            Number of sessions deleted
        """
        with self._lock:
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()

            now = datetime.now().isoformat()
            cursor.execute("DELETE FROM sessions WHERE expires_at < ?", (now,))

            conn.commit()
            deleted = cursor.rowcount
            conn.close()

            if deleted > 0:
                logger.info(f"Cleaned up {deleted} expired sessions")

            return deleted
