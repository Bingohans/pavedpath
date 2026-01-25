"""
Authentication and authorization module
Handles JWT tokens and user permissions
"""

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from datetime import datetime, timedelta
from typing import Optional
import logging
import os

from .models import User

logger = logging.getLogger(__name__)

# Security configuration
SECRET_KEY = os.getenv("JWT_SECRET_KEY", "your-secret-key-change-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60

# Security scheme
security = HTTPBearer()


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """
    Create a JWT access token
    
    Args:
        data: Data to encode in token (user_id, username, etc.)
        expires_delta: Optional custom expiration time
        
    Returns:
        Encoded JWT token string
    """
    to_encode = data.copy()
    
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({"exp": expire})
    
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def create_demo_token() -> str:
    """
    Create a demo token for testing
    
    In production, replace this with proper OAuth/OIDC integration
    """
    demo_user = {
        "user_id": "demo-user",
        "username": "demo",
        "email": "demo@example.com",
        "allowed_namespaces": ["development", "staging", "demo"],
        "is_admin": False
    }
    
    return create_access_token(demo_user)


def decode_token(token: str) -> dict:
    """
    Decode and validate JWT token
    
    Args:
        token: JWT token string
        
    Returns:
        Decoded token payload
        
    Raises:
        JWTError: If token is invalid or expired
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError as e:
        logger.warning(f"Token validation failed: {str(e)}")
        raise


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> User:
    """
    Dependency to get current authenticated user
    
    Args:
        credentials: HTTP Authorization header with Bearer token
        
    Returns:
        User object with permissions
        
    Raises:
        HTTPException: If authentication fails
    """
    token = credentials.credentials
    
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    try:
        payload = decode_token(token)
        
        user_id: str = payload.get("user_id")
        username: str = payload.get("username")
        
        if user_id is None or username is None:
            logger.warning("Token missing required fields")
            raise credentials_exception
        
        # Build User object from token
        user = User(
            user_id=user_id,
            username=username,
            email=payload.get("email"),
            allowed_namespaces=payload.get("allowed_namespaces", []),
            is_admin=payload.get("is_admin", False)
        )
        
        logger.debug(f"Authenticated user: {user.user_id}")
        return user
        
    except JWTError:
        logger.warning("JWT validation failed")
        raise credentials_exception
    except Exception as e:
        logger.error(f"Authentication error: {str(e)}")
        raise credentials_exception


def verify_namespace_access(user: User, namespace: str) -> bool:
    """
    Verify user has access to a namespace
    
    Args:
        user: User object
        namespace: Namespace to check
        
    Returns:
        True if user has access, False otherwise
    """
    if user.is_admin:
        return True
    
    return namespace in user.allowed_namespaces


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    """
    Dependency to require admin privileges
    
    Args:
        current_user: Current authenticated user
        
    Returns:
        User object if admin
        
    Raises:
        HTTPException: If user is not admin
    """
    if not current_user.is_admin:
        logger.warning(f"Non-admin user {current_user.user_id} attempted admin action")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required"
        )
    
    return current_user


# For production: integrate with your OAuth/OIDC provider
class OAuthIntegration:
    """
    Placeholder for OAuth/OIDC integration
    
    In production, implement methods to:
    - Validate OAuth tokens
    - Fetch user info from identity provider
    - Map user groups to Kubernetes namespaces
    - Sync user permissions
    """
    
    @staticmethod
    def validate_oauth_token(token: str) -> dict:
        """Validate token with OAuth provider"""
        raise NotImplementedError("OAuth integration not implemented")
    
    @staticmethod
    def get_user_info(token: str) -> dict:
        """Get user information from OAuth provider"""
        raise NotImplementedError("OAuth integration not implemented")
    
    @staticmethod
    def get_user_namespaces(user_id: str) -> list:
        """Get user's allowed namespaces from directory/LDAP"""
        raise NotImplementedError("OAuth integration not implemented")
