import threading
import time
from datetime import datetime
from typing import Dict, List
from github_client import GitHubClient
from argocd_client import ArgoCDClient

import logging

logger = logging.getLogger(__name__)


class CleanupScheduler:
    """Manages scheduled cleanup of demo deployments"""
    
    def __init__(self, k8s_client: KubernetesClient):
        self.k8s_client = k8s_client
        self.scheduled_cleanups: Dict[str, Dict] = {}
        self.lock = threading.Lock()
        self.running = False
        self.cleanup_thread = None
    
    def start(self):
        """Start the cleanup scheduler"""
        if not self.running:
            self.running = True
            self.cleanup_thread = threading.Thread(target=self._cleanup_loop, daemon=True)
            self.cleanup_thread.start()
            logger.info("Cleanup scheduler started")
    
    def stop(self):
        """Stop the cleanup scheduler"""
        self.running = False
        if self.cleanup_thread:
            self.cleanup_thread.join(timeout=5)
            logger.info("Cleanup scheduler stopped")
    
    def schedule_cleanup(
        self,
        namespace: str,
        pod_name: str,
        cleanup_time: datetime,
        cleanup_github: bool = False,
        cleanup_argocd: bool = False
    ):
        """Schedule cleanup with optional GitOps cleanup"""
        with self.lock:
            key = f"{namespace}/{pod_name}"
            self.scheduled_cleanups[key] = {
                "cleanup_time": cleanup_time,
                "cleanup_github": cleanup_github,
                "cleanup_argocd": cleanup_argocd
            }
            logger.info(f"Scheduled cleanup for {key} at {cleanup_time}")
    
    def cancel_cleanup(self, namespace: str, pod_name: str):
        """Cancel scheduled cleanup"""
        with self.lock:
            key = f"{namespace}/{pod_name}"
            if key in self.scheduled_cleanups:
                del self.scheduled_cleanups[key]
                logger.info(f"Cancelled cleanup for {key}")
    
    def _cleanup_loop(self):  # ← METODE INDE I KLASSEN!
        """Background thread that performs scheduled cleanups"""
        logger.info("Cleanup scheduler started")
        
        while self.running:
            try:
                now = datetime.utcnow()
                to_cleanup = []
                
                with self.lock:
                    for key, data in self.scheduled_cleanups.items():
                        if now >= data["cleanup_time"]:
                            to_cleanup.append((key, data))
                
                for key, data in to_cleanup:
                    namespace, pod_name = key.split("/")
                    
                    try:
                        # Import here to avoid circular import
                        from main import github_client, argocd_client
                        
                        # 1. Delete ArgoCD application
                        if data.get("cleanup_argocd") and argocd_client:
                            logger.info(f"Deleting ArgoCD application: {pod_name}")
                            try:
                                argocd_client.delete_application(pod_name, cascade=True)
                            except Exception as e:
                                logger.error(f"ArgoCD cleanup failed: {e}")
                        
                        # 2. Delete GitHub repository
                        if data.get("cleanup_github") and github_client:
                            repo_name = f"{namespace}-{pod_name}"
                            logger.info(f"Deleting GitHub repository: {repo_name}")
                            try:
                                github_client.delete_repo(repo_name)
                            except Exception as e:
                                logger.error(f"GitHub cleanup failed: {e}")
                        
                        # 3. K8s cleanup
                        logger.info(f"Cleaning up Kubernetes resources: {key}")
                        self.k8s_client.delete_pod(namespace, pod_name)
                        
                        with self.lock:
                            del self.scheduled_cleanups[key]
                        
                        logger.info(f"Cleanup completed for {key}")
                        
                    except Exception as e:
                        logger.error(f"Failed to cleanup {key}: {e}", exc_info=True)
                        with self.lock:
                            if key in self.scheduled_cleanups:
                                del self.scheduled_cleanups[key]
                
                time.sleep(10)
                
            except Exception as e:
                logger.error(f"Error in cleanup loop: {e}", exc_info=True)
                time.sleep(10)
