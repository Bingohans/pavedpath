"""
Cleanup scheduler for automatic deletion of demo deployments
Runs background tasks to delete pods after expiration time
"""

import threading
import time
from datetime import datetime
from typing import Dict, List
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
        pod_name: str,
        namespace: str,
        cleanup_time: datetime
    ):
        """
        Schedule a pod for cleanup
        
        Args:
            pod_name: Name of pod to cleanup
            namespace: Namespace of pod
            cleanup_time: When to delete the pod
        """
        key = f"{namespace}/{pod_name}"
        
        with self.lock:
            self.scheduled_cleanups[key] = {
                "pod_name": pod_name,
                "namespace": namespace,
                "cleanup_time": cleanup_time,
                "scheduled_at": datetime.utcnow()
            }
        
        logger.info(
            f"Scheduled cleanup for {key} at {cleanup_time.isoformat()}"
        )
    
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
