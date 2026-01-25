from pydantic import BaseModel, Field, validator
from typing import Optional, List
from datetime import datetime
import re


class DeploymentRequest(BaseModel):
    """Request model for pod deployment"""
    
    pod_name: str = Field(
        ...,
        min_length=1,
        max_length=63,
        description="Name of the pod (must follow Kubernetes naming conventions)"
    )
    namespace: str = Field(
        ...,
        min_length=1,
        max_length=63,
        description="Kubernetes namespace"
    )
    docker_image: str = Field(
        ...,
        description="Docker image to deploy (must be from whitelist)"
    )
    has_storage: bool = Field(
        default=False,
        description="Whether to provision persistent storage"
    )
    has_database: bool = Field(
        default=False,
        description="Whether to setup database connection"
    )
    
    # Optional fields (for metadata/logging only - not used in deployment)
    memory_request: Optional[int] = Field(
        default=256,
        description="Memory request in MB (ignored, always set to 256)"
    )
    memory_limit: Optional[int] = Field(
        default=512,
        description="Memory limit in MB (ignored, always set to 512)"
    )
    cpu_request: Optional[int] = Field(
        default=100,
        description="CPU request in millicores (ignored, always set to 100)"
    )
    cpu_limit: Optional[int] = Field(
        default=500,
        description="CPU limit in millicores (ignored, always set to 500)"
    )
    storage_size: Optional[int] = Field(
        default=10,
        description="Storage size in GB (ignored, always set to 10)"
    )
    
    @validator('pod_name')
    def validate_pod_name(cls, v):
        """Validate pod name follows Kubernetes naming rules"""
        pattern = r'^[a-z0-9]([-a-z0-9]*[a-z0-9])?$'
        if not re.match(pattern, v):
            raise ValueError(
                "Pod name must consist of lower case alphanumeric characters or '-', "
                "and must start and end with an alphanumeric character"
            )
        return v.lower()
    
    @validator('namespace')
    def validate_namespace(cls, v):
        """Validate namespace name"""
        pattern = r'^[a-z0-9]([-a-z0-9]*[a-z0-9])?$'
        if not re.match(pattern, v):
            raise ValueError(
                "Namespace must consist of lower case alphanumeric characters or '-'"
            )
        return v.lower()
    
    class Config:
        schema_extra = {
            "example": {
                "pod_name": "my-app",
                "namespace": "development",
                "docker_image": "nginx:1.25-alpine",
                "has_storage": False,
                "has_database": False
            }
        }


class DeploymentResponse(BaseModel):
    """Response model for deployment endpoint"""
    
    success: bool = Field(..., description="Whether deployment was successful")
    pod_name: str = Field(..., description="Name of the deployed pod")
    namespace: str = Field(..., description="Namespace where pod was deployed")
    status: str = Field(..., description="Current deployment status")
    message: str = Field(..., description="Deployment message")
    cleanup_at: str = Field(..., description="ISO timestamp when deployment will be deleted")
    repository_url: str = Field(..., description="GitHub repository URL (demo)")
    argocd_url: str = Field(..., description="ArgoCD application URL (demo)")
    
    class Config:
        schema_extra = {
            "example": {
                "success": True,
                "pod_name": "my-app",
                "namespace": "development",
                "status": "deploying",
                "message": "Deployment initiated successfully",
                "cleanup_at": "2025-01-24T12:35:00Z",
                "repository_url": "https://github.com/demo/development-my-app",
                "argocd_url": "https://argocd.demo.local/applications/my-app"
            }
        }


class PodStatus(BaseModel):
    """Pod status information"""
    
    name: str
    namespace: str
    status: str
    phase: str
    ready: str
    restarts: int
    age: str
    node: Optional[str] = None
    ip: Optional[str] = None
    
    class Config:
        schema_extra = {
            "example": {
                "name": "my-app",
                "namespace": "development",
                "status": "Running",
                "phase": "Running",
                "ready": "1/1",
                "restarts": 0,
                "age": "2m30s",
                "node": "worker-node-1",
                "ip": "10.244.1.5"
            }
        }


class User(BaseModel):
    """User model for authentication"""
    
    user_id: str = Field(..., description="Unique user identifier")
    username: str = Field(..., description="Username")
    email: Optional[str] = Field(None, description="User email")
    allowed_namespaces: List[str] = Field(
        default_factory=list,
        description="List of namespaces user can access"
    )
    is_admin: bool = Field(default=False, description="Whether user is admin")
    
    class Config:
        schema_extra = {
            "example": {
                "user_id": "user123",
                "username": "john.doe",
                "email": "john.doe@example.com",
                "allowed_namespaces": ["development", "staging"],
                "is_admin": False
            }
        }


class TokenResponse(BaseModel):
    """Authentication token response"""
    
    token: str = Field(..., description="JWT token")
    expires_in: int = Field(..., description="Token expiration time in seconds")
    token_type: str = Field(default="Bearer", description="Token type")
    
    class Config:
        schema_extra = {
            "example": {
                "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                "expires_in": 3600,
                "token_type": "Bearer"
            }
        }


class ErrorResponse(BaseModel):
    """Error response model"""
    
    detail: str = Field(..., description="Error message")
    timestamp: str = Field(..., description="Error timestamp")
    
    class Config:
        schema_extra = {
            "example": {
                "detail": "Invalid pod name format",
                "timestamp": "2025-01-24T12:00:00Z"
            }
        }
