"""
Kubernetes Paved Roads Deployment API
Secure backend for pod deployment with validation and rate limiting
"""

from fastapi import FastAPI, HTTPException, Depends, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from datetime import datetime, timedelta
from typing import Optional
import logging

from .models import DeploymentRequest, DeploymentResponse, User
from .validator import DeploymentValidator
from .auth import get_current_user, create_demo_token
from .k8s_client import KubernetesClient
from .cleanup import CleanupScheduler

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="K8s Paved Roads Deployment API",
    description="Secure Kubernetes deployment service with built-in validation",
    version="1.0.0"
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:8080",
        "https://yourdomain.com"  # Replace with your actual domain
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["*"],
)

# Rate limiting
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Initialize services
validator = DeploymentValidator()
k8s_client = KubernetesClient()
cleanup_scheduler = CleanupScheduler(k8s_client)

# Start cleanup scheduler
cleanup_scheduler.start()


@app.get("/")
async def root():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "k8s-paved-roads-api",
        "version": "1.0.0",
        "timestamp": datetime.utcnow().isoformat()
    }


@app.get("/api/health")
async def health_check():
    """Detailed health check"""
    try:
        k8s_healthy = k8s_client.check_health()
        return {
            "status": "healthy",
            "kubernetes": "connected" if k8s_healthy else "disconnected",
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error(f"Health check failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service unhealthy"
        )


@app.post("/api/demo/token")
@limiter.limit("5/minute")
async def get_demo_token(request: Request):
    """
    Generate a demo authentication token (for testing only)
    In production, this would be replaced with proper OAuth/OIDC
    """
    try:
        token = create_demo_token()
        return {
            "token": token,
            "expires_in": 3600,
            "token_type": "Bearer"
        }
    except Exception as e:
        logger.error(f"Failed to create demo token: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate token"
        )


@app.post("/api/deploy", response_model=DeploymentResponse)
@limiter.limit("3/hour")  # Max 3 deployments per hour per IP
async def deploy_pod(
    request: Request,
    deployment_request: DeploymentRequest,
    current_user: User = Depends(get_current_user)
):
    """
    Deploy a pod to Kubernetes cluster with full validation
    
    Security measures:
    - Rate limited to 3 deployments per hour
    - Requires authentication
    - Validates all inputs server-side
    - Enforces resource limits
    - Only allows whitelisted images
    """
    
    logger.info(f"Deployment request from user {current_user.user_id}: {deployment_request.pod_name}")
    
    try:
        # 1. Validate and sanitize input
        validated_data = validator.validate_deployment_request(
            deployment_request.dict(),
            current_user
        )
        
        logger.info(f"Validation passed for pod: {validated_data['pod_name']}")
        
        # 2. Check for existing deployment with same name
        if k8s_client.pod_exists(validated_data['pod_name'], validated_data['namespace']):
            logger.warning(f"Pod already exists: {validated_data['pod_name']}")
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Pod '{validated_data['pod_name']}' already exists in namespace '{validated_data['namespace']}'"
            )
        
        # 3. Deploy to Kubernetes
        deployment_result = k8s_client.deploy_pod(validated_data)
        
        logger.info(f"Successfully deployed pod: {validated_data['pod_name']}")
        
        # 4. Schedule cleanup (5 minutes for demo)
        cleanup_time = datetime.utcnow() + timedelta(minutes=5)
        cleanup_scheduler.schedule_cleanup(
            pod_name=validated_data['pod_name'],
            namespace=validated_data['namespace'],
            cleanup_time=cleanup_time
        )
        
        logger.info(f"Scheduled cleanup for {validated_data['pod_name']} at {cleanup_time}")
        
        # 5. Return deployment info
        return DeploymentResponse(
            success=True,
            pod_name=validated_data['pod_name'],
            namespace=validated_data['namespace'],
            status="deploying",
            message="Deployment initiated successfully",
            cleanup_at=cleanup_time.isoformat(),
            repository_url=f"https://github.com/demo/{validated_data['namespace']}-{validated_data['pod_name']}",
            argocd_url=f"https://argocd.demo.local/applications/{validated_data['pod_name']}"
        )
        
    except ValueError as e:
        logger.warning(f"Validation error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except PermissionError as e:
        logger.warning(f"Permission error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Deployment failed: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Deployment failed. Please try again or contact support."
        )


@app.get("/api/deployment/{namespace}/{pod_name}")
async def get_deployment_status(
    namespace: str,
    pod_name: str,
    current_user: User = Depends(get_current_user)
):
    """Get current status of a deployment"""
    
    try:
        # Verify user has access to this namespace
        if namespace not in current_user.allowed_namespaces:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this namespace"
            )
        
        # Get pod status from Kubernetes
        status_info = k8s_client.get_pod_status(pod_name, namespace)
        
        if not status_info:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Deployment not found"
            )
        
        return status_info
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get deployment status: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve deployment status"
        )


@app.delete("/api/deployment/{namespace}/{pod_name}")
async def delete_deployment(
    namespace: str,
    pod_name: str,
    current_user: User = Depends(get_current_user)
):
    """Manually delete a deployment"""
    
    logger.info(f"Delete request from user {current_user.user_id}: {pod_name}")
    
    try:
        # Verify user has access to this namespace
        if namespace not in current_user.allowed_namespaces:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this namespace"
            )
        
        # Delete pod and associated resources
        success = k8s_client.delete_pod(pod_name, namespace)
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Deployment not found"
            )
        
        # Cancel scheduled cleanup
        cleanup_scheduler.cancel_cleanup(pod_name, namespace)
        
        logger.info(f"Successfully deleted pod: {pod_name}")
        
        return {
            "success": True,
            "message": f"Deployment '{pod_name}' deleted successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete deployment: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete deployment"
        )


@app.get("/api/deployments")
async def list_deployments(
    namespace: Optional[str] = None,
    current_user: User = Depends(get_current_user)
):
    """List all deployments (filtered by user's accessible namespaces)"""
    
    try:
        # Filter namespaces by user permissions
        namespaces = [namespace] if namespace else current_user.allowed_namespaces
        
        # Verify access to requested namespace
        if namespace and namespace not in current_user.allowed_namespaces:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this namespace"
            )
        
        deployments = k8s_client.list_pods(namespaces)
        
        return {
            "deployments": deployments,
            "total": len(deployments)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to list deployments: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve deployments"
        )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler for unhandled errors"""
    logger.error(f"Unhandled exception: {str(exc)}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "detail": "An unexpected error occurred. Please contact support.",
            "timestamp": datetime.utcnow().isoformat()
        }
    )


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    logger.info("Shutting down API server...")
    cleanup_scheduler.stop()
    k8s_client.close()
    logger.info("Shutdown complete")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
