import logging
import os
from datetime import datetime, timedelta

from argocd_client import ArgoCDClient
from auth import create_demo_token, get_current_user
from cleanup import CleanupScheduler
from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from github_client import GitHubClient
from k8s_client import KubernetesClient
from models import DeploymentRequest, DeploymentResponse, User
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from validator import DeploymentValidator

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_ORG = os.getenv("GITHUB_ORG")
ARGOCD_URL = os.getenv("ARGOCD_URL", "https://argocd-server.argocd.svc.cluster.local")
ARGOCD_TOKEN = os.getenv("ARGOCD_TOKEN")

github_client = None
argocd_client = None

AUTO_CLEANUP_MINUTES = int(os.getenv("AUTO_CLEANUP_MINUTES", "5"))  # ← ADD THIS!
RATE_LIMIT_PER_HOUR = int(os.getenv("RATE_LIMIT_PER_HOUR", "3"))

if GITHUB_TOKEN:
    from github_client import GitHubClient

    try:
        github_client = GitHubClient(token=GITHUB_TOKEN, org_name=GITHUB_ORG)
        logger.info("GitHub client initialized")
    except Exception as e:
        logger.error(f"Failed to initialize GitHub client: {e}")

if ARGOCD_TOKEN and ARGOCD_URL:
    from argocd_client import ArgoCDClient

    try:
        argocd_client = ArgoCDClient(url=ARGOCD_URL, token=ARGOCD_TOKEN)
        logger.info("ArgoCD client initialized")
    except Exception as e:
        logger.error(f"Failed to initialize ArgoCD client: {e}")

# Initialize FastAPI app
app = FastAPI(
    title="K8s Paved Roads Deployment API",
    description="Secure Kubernetes deployment service with built-in validation",
    version="1.0.0",
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:8080",
        "https://yourdomain.com",  # Replace with your actual domain
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
        "timestamp": datetime.utcnow().isoformat(),
    }


@app.get("/api/health")
async def health_check():
    """Detailed health check"""
    try:
        k8s_healthy = k8s_client.check_health()
        return {
            "status": "healthy",
            "kubernetes": "connected" if k8s_healthy else "disconnected",
            "timestamp": datetime.utcnow().isoformat(),
        }
    except Exception as e:
        logger.error(f"Health check failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Service unhealthy"
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
        return {"token": token, "expires_in": 3600, "token_type": "Bearer"}
    except Exception as e:
        logger.error(f"Failed to create demo token: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate token",
        )


@app.post("/api/deploy", response_model=DeploymentResponse)
async def deploy_pod(
    deployment_request: DeploymentRequest,
    current_user: User = Depends(get_current_user),
):
    """
    Deploy pod via GitOps (GitHub + ArgoCD)
    """
    try:
        # 1. Validate request
        validated_data = validator.validate_deployment_request(
            deployment_request,  # ← Send hele request object
            current_user,
        )

        logger.info(
            f"Deploying {validated_data['pod_name']} to {validated_data['namespace']} via GitOps"
        )

        # 2. Check if GitOps is enabled
        if not github_client or not argocd_client:
            # Fallback to direct K8s deployment (demo mode)
            logger.warning("GitOps not configured, using direct K8s deployment")

            # Use existing k8s_client deployment
            result = k8s_client.deploy_pod(validated_data)

            # Schedule cleanup
            cleanup_time = datetime.utcnow() + timedelta(minutes=AUTO_CLEANUP_MINUTES)
            cleanup_scheduler.schedule_cleanup(
                validated_data["namespace"], validated_data["pod_name"], cleanup_time
            )

            return DeploymentResponse(
                success=True,
                message=f"Pod {validated_data['pod_name']} deployed successfully (demo mode)",
                pod_name=validated_data["pod_name"],
                namespace=validated_data["namespace"],
                status="deploying",
                cleanup_at=cleanup_time,
                repository_url=f"https://github.com/demo/{validated_data['namespace']}-{validated_data['pod_name']}",
                argocd_url=f"{ARGOCD_URL}/applications/{validated_data['pod_name']}",
            )

        # 3. GitOps Mode: Create GitHub repository
        try:
            repo_url = github_client.create_deployment_repo(
                pod_name=validated_data["pod_name"],
                namespace=validated_data["namespace"],
                docker_image=validated_data["docker_image"],
                has_storage=deployment_request.has_storage,
                has_database=deployment_request.has_database,
                resource_limits=validated_data["resource_limits"],
            )
            logger.info(f"GitHub repository created: {repo_url}")
        except Exception as e:
            logger.error(f"Failed to create GitHub repo: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to create GitHub repository: {str(e)}",
            )

        # 4. Create ArgoCD Application
        try:
            argocd_client.create_application(
                app_name=validated_data["pod_name"],
                repo_url=repo_url,
                namespace=validated_data["namespace"],
                path="k8s",
                auto_sync=True,
            )
            logger.info(f"ArgoCD application created: {validated_data['pod_name']}")
        except Exception as e:
            logger.error(f"Failed to create ArgoCD app: {e}")
            # Try to cleanup GitHub repo
            repo_name = f"{validated_data['namespace']}-{validated_data['pod_name']}"
            github_client.delete_repo(repo_name)

            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to create ArgoCD application: {str(e)}",
            )

        # 5. Schedule cleanup (for both GitHub and ArgoCD)
        cleanup_time = datetime.utcnow() + timedelta(minutes=AUTO_CLEANUP_MINUTES)
        cleanup_scheduler.schedule_cleanup(
            validated_data["namespace"],
            validated_data["pod_name"],
            cleanup_time,
            cleanup_github=True,  # NEW: Also cleanup GitHub repo
            cleanup_argocd=True,  # NEW: Also cleanup ArgoCD app
        )

        # 6. Return response with REAL URLs
        argocd_app_url = f"{ARGOCD_URL}/applications/{validated_data['pod_name']}"

        return DeploymentResponse(
            success=True,
            message=f"Deployment initiated via GitOps for {validated_data['pod_name']}",
            pod_name=validated_data["pod_name"],
            namespace=validated_data["namespace"],
            status="syncing",  # ArgoCD is syncing
            cleanup_at=cleanup_time,
            repository_url=repo_url,  # REAL GitHub URL
            argocd_url=argocd_app_url,  # REAL ArgoCD URL
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Deployment failed: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Deployment failed: {str(e)}",
        )


@app.get("/api/deployment/{namespace}/{pod_name}/argocd-status")
async def get_argocd_status(
    namespace: str, pod_name: str, current_user: User = Depends(get_current_user)
):
    """Get ArgoCD sync and health status"""

    if not argocd_client:
        return {
            "sync_status": "unknown",
            "health_status": "unknown",
            "message": "ArgoCD not configured",
        }

    try:
        sync_status = argocd_client.get_application_status(pod_name)
        health_status = argocd_client.get_application_health(pod_name)

        return {
            "sync_status": sync_status or "not_found",
            "health_status": health_status or "not_found",
            "argocd_url": f"{ARGOCD_URL}/applications/{pod_name}",
        }
    except Exception as e:
        logger.error(f"Failed to get ArgoCD status: {e}")
        return {"sync_status": "error", "health_status": "error", "message": str(e)}


@app.delete("/api/deployment/{namespace}/{pod_name}")
async def delete_deployment(
    namespace: str, pod_name: str, current_user: User = Depends(get_current_user)
):
    """Manually delete a deployment"""

    logger.info(f"Delete request from user {current_user.user_id}: {pod_name}")

    try:
        # Verify user has access to this namespace
        if namespace not in current_user.allowed_namespaces:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this namespace",
            )

        # Delete pod and associated resources
        success = k8s_client.delete_pod(pod_name, namespace)

        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Deployment not found"
            )

        # Cancel scheduled cleanup
        cleanup_scheduler.cancel_cleanup(pod_name, namespace)

        logger.info(f"Successfully deleted pod: {pod_name}")

        return {
            "success": True,
            "message": f"Deployment '{pod_name}' deleted successfully",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete deployment: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete deployment",
        )


@app.get("/api/deployment/{namespace}/{pod_name}/argocd")  # ← Ændret path!
async def get_argocd_status(
    namespace: str, pod_name: str, current_user: User = Depends(get_current_user)
):
    """Get ArgoCD sync and health status"""

    if not argocd_client:
        return {
            "sync_status": "unknown",
            "health_status": "unknown",
            "message": "ArgoCD not configured",
        }

    try:
        sync_status = argocd_client.get_application_status(pod_name)
        health_status = argocd_client.get_application_health(pod_name)

        return {
            "sync_status": sync_status or "not_found",
            "health_status": health_status or "not_found",
            "argocd_url": f"{ARGOCD_URL}/applications/{pod_name}",
        }
    except Exception as e:
        logger.error(f"Failed to get ArgoCD status: {e}")
        return {"sync_status": "error", "health_status": "error", "message": str(e)}


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler for unhandled errors"""
    logger.error(f"Unhandled exception: {str(exc)}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "detail": "An unexpected error occurred. Please contact support.",
            "timestamp": datetime.utcnow().isoformat(),
        },
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

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True, log_level="info")
