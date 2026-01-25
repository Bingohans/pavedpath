import threading
import time
from datetime import datetime
from typing import Dict, List
from github_client import GitHubClient
from argocd_client import ArgoCDClient

import logging

logger = logging.getLogger(__name__)


class CleanupScheduler:
    """
    Background scheduler for automatic pod cleanup
    Deletes demo pods after 5 minutes
    """
    
    def __init__(self, k8s_client):
        """
        Initialize cleanup scheduler
        
        Args:
            k8s_client: KubernetesClient instance
        """
        self.k8s_client = k8s_client
        self.scheduled_cleanups: Dict[str, Dict] = {}
        self.lock = threading.Lock()
        self.running = False
        self.thread = None
        
        logger.info("Cleanup scheduler initialized")
    
    def start(self):
        """Start the cleanup scheduler thread"""
        if self.running:
            logger.warning("Cleanup scheduler already running")
            return
        
        self.running = True
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()
        
        logger.info("Cleanup scheduler started")
    
    def stop(self):
        """Stop the cleanup scheduler thread"""
        self.running = False
        
        if self.thread:
            self.thread.join(timeout=5)
        
        logger.info("Cleanup scheduler stopped")
    
        def schedule_cleanup(
            self,
            namespace: str,
            pod_name: str,
            cleanup_time: datetime,
            cleanup_github: bool = False,
            cleanup_argocd: bool = False
        ):
            """
            Schedule cleanup for deployment
    
            Args:
                namespace: Kubernetes namespace
                pod_name: Pod name
                cleanup_time: When to cleanup
                cleanup_github: Also delete GitHub repository
                cleanup_argocd: Also delete ArgoCD application
            """
            with self.lock:
                key = f"{namespace}/{pod_name}"
                self.scheduled_cleanups[key] = {
                    "cleanup_time": cleanup_time,
                    "cleanup_github": cleanup_github,
                    "cleanup_argocd": cleanup_argocd
                }
                logger.info(f"Scheduled cleanup for {key} at {cleanup_time}")
    
    def cancel_cleanup(self, pod_name: str, namespace: str):
        """
        Cancel a scheduled cleanup
        
        Args:
            pod_name: Name of pod
            namespace: Namespace of pod
        """
        key = f"{namespace}/{pod_name}"
        
        with self.lock:
            if key in self.scheduled_cleanups:
                del self.scheduled_cleanups[key]
                logger.info(f"Cancelled cleanup for {key}")
    
    def _run(self):
        """
        Main cleanup loop
        Runs every 10 seconds to check for expired pods
        """
        logger.info("Cleanup scheduler loop started")
        
        while self.running:
            try:
                self._cleanup_expired_pods()
                time.sleep(10)  # Check every 10 seconds
            except Exception as e:
                logger.error(f"Error in cleanup loop: {str(e)}", exc_info=True)
                time.sleep(10)
        
        logger.info("Cleanup scheduler loop stopped")
    
    def _cleanup_expired_pods(self):
        """Check for and cleanup expired pods"""
        now = datetime.utcnow()
        to_cleanup = []
        
        # Find expired pods
        with self.lock:
            for key, info in self.scheduled_cleanups.items():
                if now >= info["cleanup_time"]:
                    to_cleanup.append((key, info))
        
        # Cleanup expired pods
        for key, info in to_cleanup:
            try:
                logger.info(f"Cleaning up expired pod: {key}")
                
                success = self.k8s_client.delete_pod(
                    pod_name=info["pod_name"],
                    namespace=info["namespace"]
                )
                
                if success:
                    logger.info(f"Successfully cleaned up pod: {key}")
                else:
                    logger.warning(f"Pod not found during cleanup: {key}")
                
                # Remove from scheduled list
                with self.lock:
                    if key in self.scheduled_cleanups:
                        del self.scheduled_cleanups[key]
                
            except Exception as e:
                logger.error(f"Failed to cleanup pod {key}: {str(e)}")
    
    def get_scheduled_cleanups(self) -> List[Dict]:
        """Get list of all scheduled cleanups"""
        with self.lock:
            return list(self.scheduled_cleanups.values())
    
    def get_cleanup_info(self, pod_name: str, namespace: str) -> Dict:
        """Get cleanup info for specific pod"""
        key = f"{namespace}/{pod_name}"
        
        with self.lock:
            return self.scheduled_cleanups.get(key)

    def _cleanup_loop(self):
    """Background thread that performs scheduled cleanups"""
    logger.info("Cleanup scheduler started")
    
    # Get GitOps clients (from main.py or pass as parameters)
    from main import github_client, argocd_client
    
    while self.running:
        try:
            now = datetime.utcnow()
            to_cleanup = []
            
            with self.lock:
                for key, data in self.scheduled_cleanups.items():
                    if now >= data["cleanup_time"]:
                        to_cleanup.append((key, data))
            
            # Perform cleanups
            for key, data in to_cleanup:
                namespace, pod_name = key.split("/")
                
                try:
                    # 1. Delete ArgoCD application (if enabled)
                    if data.get("cleanup_argocd") and argocd_client:
                        logger.info(f"Deleting ArgoCD application: {pod_name}")
                        argocd_client.delete_application(pod_name, cascade=True)
                    
                    # 2. Delete GitHub repository (if enabled)
                    if data.get("cleanup_github") and github_client:
                        repo_name = f"{namespace}-{pod_name}"
                        logger.info(f"Deleting GitHub repository: {repo_name}")
                        github_client.delete_repo(repo_name)
                    
                    # 3. Direct K8s cleanup (for demo mode or as backup)
                    logger.info(f"Cleaning up Kubernetes resources: {key}")
                    self.k8s_client.delete_pod(namespace, pod_name)
                    
                    # Remove from schedule
                    with self.lock:
                        del self.scheduled_cleanups[key]
                    
                    logger.info(f"Cleanup completed for {key}")
                    
                except Exception as e:
                    logger.error(f"Failed to cleanup {key}: {e}", exc_info=True)
                    # Remove from schedule anyway to avoid infinite retries
                    with self.lock:
                        if key in self.scheduled_cleanups:
                            del self.scheduled_cleanups[key]
            
            # Sleep before next check
            time.sleep(10)
            
        except Exception as e:
            logger.error(f"Error in cleanup loop: {e}", exc_info=True)
            time.sleep(10)
