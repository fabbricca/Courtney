# GLaDOS Authentication Module

JWT-based authentication system with multi-user support and role-based access control (RBAC).

## Features

- **JWT Authentication**: Stateless token-based authentication
- **Multi-User Support**: Isolated data per user
- **RBAC**: Role and permission system for tool access control
- **Secure**: bcrypt password hashing, token expiration, session management
- **Thread-Safe**: All database operations protected by RLock

## Quick Start

### 1. Install Dependencies

```bash
pip install pyjwt bcrypt
```

Or using the project requirements:

```bash
pip install -e .
```

### 2. Create Admin User

```bash
python scripts/create_admin.py
```

This will prompt for:
- Username
- Email
- Password

The admin user has full permissions (admin:*).

### 3. Use in Code

```python
from pathlib import Path
from glados.auth import UserManager

# Initialize
manager = UserManager(
    db_path=Path("data/users.db"),
    secret_key="your-secret-key-here"  # Load from env in production!
)

# Login
result = manager.login("username", "password")
if result:
    access_token, refresh_token = result
    print(f"Access token: {access_token}")
else:
    print("Login failed")

# Verify token
payload = manager.verify_token(access_token)
if payload:
    print(f"User: {payload.username}")
    print(f"Permissions: {payload.permissions}")

# Check permission
if manager.has_permission(payload, "tool:web_search"):
    print("User can use web search")
```

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│ UserManager                                             │
│  - login(username, password)                            │
│  - verify_token(token)                                  │
│  - has_permission(payload, permission)                  │
│  - refresh_access_token(refresh_token)                  │
└────────────────┬────────────────────────────────────────┘
                 │
         ┌───────┴────────┐
         │                │
    ┌────▼────┐     ┌────▼────┐
    │  JWT    │     │Database │
    │ Handler │     │ (SQLite)│
    └─────────┘     └─────────┘
```

## Database Schema

### Users
- `user_id` (UUID, primary key)
- `username` (unique)
- `email` (unique)
- `password_hash` (bcrypt)
- `created_at`
- `is_active`
- `is_admin`

### Roles
- `role_id` (UUID, primary key)
- `name` (unique)
- `description`

### Permissions
- `permission_id` (UUID, primary key)
- `name` (unique, e.g., "tool:web_search")
- `description`
- `resource`

### User-Role-Permission Relationships
- `user_roles` (many-to-many)
- `role_permissions` (many-to-many)

### Sessions
- `session_id` (UUID, primary key)
- `user_id`
- `token_jti` (JWT ID for revocation)
- `created_at`
- `expires_at`
- `last_activity`
- `ip_address` (optional)

## JWT Token Structure

### Access Token (1 hour)

```json
{
  "sub": "user-uuid",
  "user_id": "user-uuid",
  "username": "john_doe",
  "email": "john@example.com",
  "roles": ["user", "developer"],
  "permissions": [
    "chat:send",
    "memory:read",
    "memory:write",
    "tool:web_search"
  ],
  "iat": 1702202400,
  "exp": 1702206000,
  "jti": "unique-token-id",
  "type": "access"
}
```

### Refresh Token (30 days)

```json
{
  "sub": "user-uuid",
  "username": "john_doe",
  "iat": 1702202400,
  "exp": 1704794400,
  "jti": "unique-refresh-id",
  "type": "refresh"
}
```

## Permission Checking

### Exact Match

```python
has_permission(payload, "chat:send")
# Returns True if "chat:send" in payload.permissions
```

### Wildcard Match

```python
# User has "tool:*" permission
has_permission(payload, "tool:web_search")   # True
has_permission(payload, "tool:code_exec")    # True
has_permission(payload, "memory:write")      # False
```

### Admin Wildcard

```python
# User has "admin:*" permission
has_permission(payload, "anything:goes")  # True (admin has ALL permissions)
```

## Testing

Run tests with pytest:

```bash
pytest tests/unit/test_auth_database.py -v
pytest tests/unit/test_jwt.py -v
pytest tests/unit/test_user_manager.py -v
```

## Security Best Practices

### Production Deployment

1. **Secret Key**: Load from environment variable, NOT hardcoded
   ```python
   import os
   secret_key = os.environ.get("GLADOS_JWT_SECRET")
   if not secret_key:
       raise ValueError("GLADOS_JWT_SECRET not set")
   ```

2. **HTTPS Only**: Always use HTTPS in production to protect tokens

3. **Token Storage**:
   - Client: Store in memory or secure storage (NOT localStorage)
   - Server: Store JWT secret securely

4. **Password Requirements**: Enforce strong passwords
   - Minimum 12 characters
   - Mix of uppercase, lowercase, numbers, special chars

5. **Rate Limiting**: Implement login attempt rate limiting

6. **Session Cleanup**: Periodically clean expired sessions
   ```python
   manager.db.cleanup_expired_sessions()
   ```

## Next Steps

To integrate authentication with the GLaDOS server:

1. **Protocol Changes**: Add auth markers to network protocol
2. **Server Middleware**: Verify JWT on connection
3. **Memory Isolation**: Add user_id to memory classes
4. **RBAC Tools**: Filter tools based on permissions

See [AUTH_IMPLEMENTATION.md](../../../AUTH_IMPLEMENTATION.md) for detailed implementation guide.
