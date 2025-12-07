# ============================================================
# FILE: backend/app/core/security.py
# PURPOSE: JWT authentication and authorization for multi-tenancy
# ============================================================

"""
Security layer for legal RAG system.

Features:
1. JWT token generation and validation
2. User authentication
3. Organization-based multi-tenancy
4. Role-based access control (RBAC)
"""

from datetime import datetime, timedelta
from typing import Optional, Dict, Any
import logging

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from pydantic import BaseModel

from app.core.config import settings

logger = logging.getLogger(__name__)

# Security scheme
security = HTTPBearer()


class TokenData(BaseModel):
    """Data stored in JWT token"""
    user_id: str
    org_id: str
    email: Optional[str] = None
    is_admin: bool = False
    roles: list = []


class User(BaseModel):
    """User model from token"""
    user_id: str
    org_id: str
    email: Optional[str] = None
    is_admin: bool = False
    roles: list = []


def create_access_token(
    user_id: str,
    org_id: str,
    email: Optional[str] = None,
    is_admin: bool = False,
    roles: list = None,
    expires_delta: Optional[timedelta] = None
) -> str:
    """
    Create JWT access token.

    Args:
        user_id: Unique user identifier
        org_id: Organization identifier (for multi-tenancy)
        email: User email
        is_admin: Whether user has admin privileges
        roles: List of user roles
        expires_delta: Token expiration time

    Returns:
        Encoded JWT token
    """
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(
            minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
        )

    payload = {
        "sub": user_id,  # Subject (user ID)
        "org_id": org_id,  # Organization ID (critical for multi-tenancy)
        "email": email,
        "is_admin": is_admin,
        "roles": roles or [],
        "exp": expire,  # Expiration
        "iat": datetime.utcnow(),  # Issued at
    }

    encoded_jwt = jwt.encode(
        payload,
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM
    )

    logger.info(f"Created token for user={user_id}, org={org_id}")
    return encoded_jwt


def decode_token(token: str) -> TokenData:
    """
    Decode and validate JWT token.

    Args:
        token: JWT token string

    Returns:
        TokenData with user information

    Raises:
        HTTPException: If token is invalid or expired
    """
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM]
        )

        user_id: str = payload.get("sub")
        org_id: str = payload.get("org_id")

        if user_id is None or org_id is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token: missing user_id or org_id",
                headers={"WWW-Authenticate": "Bearer"},
            )

        token_data = TokenData(
            user_id=user_id,
            org_id=org_id,
            email=payload.get("email"),
            is_admin=payload.get("is_admin", False),
            roles=payload.get("roles", [])
        )

        return token_data

    except JWTError as e:
        logger.error(f"Token validation failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> User:
    """
    Dependency to get current authenticated user from JWT token.

    Usage:
    ```python
    @router.get("/protected")
    async def protected_route(current_user: User = Depends(get_current_user)):
        return {"user_id": current_user.user_id, "org_id": current_user.org_id}
    ```

    Args:
        credentials: HTTP Bearer token from request header

    Returns:
        User object with user_id and org_id

    Raises:
        HTTPException: If token is missing or invalid
    """
    token = credentials.credentials

    token_data = decode_token(token)

    user = User(
        user_id=token_data.user_id,
        org_id=token_data.org_id,
        email=token_data.email,
        is_admin=token_data.is_admin,
        roles=token_data.roles
    )

    logger.debug(f"Authenticated user: {user.user_id} (org: {user.org_id})")
    return user


async def get_current_admin_user(
    current_user: User = Depends(get_current_user)
) -> User:
    """
    Dependency to require admin privileges.

    Usage:
    ```python
    @router.post("/admin/corpus")
    async def admin_route(admin_user: User = Depends(get_current_admin_user)):
        # Only admins can access
        pass
    ```

    Args:
        current_user: Current authenticated user

    Returns:
        User object (if admin)

    Raises:
        HTTPException: If user is not admin
    """
    if not current_user.is_admin:
        logger.warning(
            f"Access denied: User {current_user.user_id} attempted admin action"
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required"
        )

    return current_user


def verify_org_access(
    resource_org_id: str,
    current_user: User
) -> bool:
    """
    Verify user has access to organization resource.

    Args:
        resource_org_id: Organization ID of the resource
        current_user: Current authenticated user

    Returns:
        True if user has access

    Raises:
        HTTPException: If user doesn't have access
    """
    if current_user.org_id != resource_org_id and not current_user.is_admin:
        logger.warning(
            f"Access denied: User {current_user.user_id} (org: {current_user.org_id}) "
            f"attempted to access resource from org: {resource_org_id}"
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: resource belongs to different organization"
        )

    return True


# ============================================================
# TEST TOKEN GENERATION (FOR DEVELOPMENT/TESTING ONLY)
# ============================================================

def create_test_token(
    user_id: str = "test_user_001",
    org_id: str = "test_org_001",
    is_admin: bool = False
) -> str:
    """
    Create test JWT token for development/testing.

    WARNING: Do not use in production!

    Args:
        user_id: Test user ID
        org_id: Test organization ID
        is_admin: Admin flag

    Returns:
        Test JWT token
    """
    return create_access_token(
        user_id=user_id,
        org_id=org_id,
        email=f"{user_id}@example.com",
        is_admin=is_admin,
        expires_delta=timedelta(days=1)  # Long expiry for testing
    )


def print_test_tokens():
    """Print test tokens for manual testing"""
    print("\n" + "="*60)
    print("TEST JWT TOKENS (for development/testing)")
    print("="*60)

    # Regular user token
    user_token = create_test_token(
        user_id="lawyer_001",
        org_id="law_firm_abc",
        is_admin=False
    )
    print("\n1. Regular User Token:")
    print(f"   User: lawyer_001")
    print(f"   Org: law_firm_abc")
    print(f"   Token: {user_token}")

    # Admin user token
    admin_token = create_test_token(
        user_id="admin_001",
        org_id="system",
        is_admin=True
    )
    print("\n2. Admin User Token:")
    print(f"   User: admin_001")
    print(f"   Org: system")
    print(f"   Token: {admin_token}")

    # Another org user
    user2_token = create_test_token(
        user_id="lawyer_002",
        org_id="law_firm_xyz",
        is_admin=False
    )
    print("\n3. User from Different Org:")
    print(f"   User: lawyer_002")
    print(f"   Org: law_firm_xyz")
    print(f"   Token: {user2_token}")

    print("\n" + "="*60)
    print("Use these tokens in Authorization header:")
    print('Authorization: Bearer <token>')
    print("="*60 + "\n")


if __name__ == "__main__":
    # Generate test tokens when run directly
    print_test_tokens()


# End of file
