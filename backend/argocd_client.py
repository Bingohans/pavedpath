# backend/argocd_client.py
"""
ArgoCD integration for creating and managing applications
"""

import requests
from typing import Dict, Optional
import logging
import json

logger = logging.getLogger(__name__)


class ArgoCDClient:
    """Manages ArgoCD Application creation and lifecycle"""
    
    def __init__(self, url: str, token: str):
        """
        Initialize ArgoCD client
        
        Args:
            url: ArgoCD server URL (e.g., https://argocd.example.com)
            token: ArgoCD authentication token
        """
        self.url = url.rstrip('/')
        self.token = token
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
    
    def create_application(
        self,
        app_name: str,
        repo_url: str,
        namespace: str,
        path: str = "k8s",
        auto_sync: bool = True
    ) -> Dict:
        """
        Create ArgoCD Application
        
        Args:
            app_name: Application name (should match pod name)
            repo_url: GitHub repository URL
            namespace: Target Kubernetes namespace
            path: Path to manifests in repo (default: k8s)
            auto_sync: Enable auto-sync
            
        Returns:
            Dict: Application details
        """
        
        logger.info(f"Creating ArgoCD application: {app_name}")
        
        # Application specification
        app_spec = {
            "apiVersion": "argoproj.io/v1alpha1",
            "kind": "Application",
            "metadata": {
                "name": app_name,
                "namespace": "argocd",
                "labels": {
                    "created-by": "paved-roads",
                    "managed": "true"
                },
                "finalizers": [
                    "resources-finalizer.argocd.argoproj.io"
                ]
            },
            "spec": {
                "project": "default",
                "source": {
                    "repoURL": repo_url,
                    "targetRevision": "main",
                    "path": path
                },
                "destination": {
                    "server": "https://kubernetes.default.svc",
                    "namespace": namespace
                },
                "syncPolicy": {
                    "automated": {
                        "prune": True,
                        "selfHeal": True,
                        "allowEmpty": False
                    } if auto_sync else None,
                    "syncOptions": [
                        "CreateNamespace=true"
                    ],
                    "retry": {
                        "limit": 5,
                        "backoff": {
                            "duration": "5s",
                            "factor": 2,
                            "maxDuration": "3m"
                        }
                    }
                }
            }
        }
        
        try:
            response = requests.post(
                f"{self.url}/api/v1/applications",
                headers=self.headers,
                json=app_spec,
                timeout=10
                verify=False
            )
            
            if response.status_code in [200, 201]:
                logger.info(f"ArgoCD application created: {app_name}")
                return response.json()
            else:
                logger.error(f"Failed to create application: {response.status_code} - {response.text}")
                response.raise_for_status()
                
        except requests.exceptions.RequestException as e:
            logger.error(f"ArgoCD API error: {e}")
            raise
    
    def get_application(self, app_name: str) -> Optional[Dict]:
        """Get application details"""
        try:
            response = requests.get(
                f"{self.url}/api/v1/applications/{app_name}",
                headers=self.headers,
                timeout=10
            )
            
            if response.status_code == 200:
                return response.json()
            elif response.status_code == 404:
                return None
            else:
                response.raise_for_status()
                
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to get application {app_name}: {e}")
            return None
    
    def sync_application(self, app_name: str) -> bool:
        """Trigger manual sync"""
        try:
            response = requests.post(
                f"{self.url}/api/v1/applications/{app_name}/sync",
                headers=self.headers,
                json={},
                timeout=10
            )
            
            if response.status_code == 200:
                logger.info(f"Sync triggered for: {app_name}")
                return True
            else:
                logger.error(f"Sync failed: {response.status_code}")
                return False
                
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to sync {app_name}: {e}")
            return False
    
    def delete_application(self, app_name: str, cascade: bool = True) -> bool:
        """
        Delete application
        
        Args:
            app_name: Application name
            cascade: If True, delete all resources (default: True)
        """
        try:
            params = {"cascade": str(cascade).lower()}
            
            response = requests.delete(
                f"{self.url}/api/v1/applications/{app_name}",
                headers=self.headers,
                params=params,
                timeout=10
            )
            
            if response.status_code in [200, 204]:
                logger.info(f"Deleted ArgoCD application: {app_name}")
                return True
            else:
                logger.error(f"Delete failed: {response.status_code}")
                return False
                
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to delete {app_name}: {e}")
            return False
    
    def get_application_status(self, app_name: str) -> Optional[str]:
        """
        Get application sync status
        
        Returns:
            str: One of: Synced, OutOfSync, Unknown, None (if app doesn't exist)
        """
        app = self.get_application(app_name)
        if not app:
            return None
        
        return app.get("status", {}).get("sync", {}).get("status", "Unknown")
    
    def get_application_health(self, app_name: str) -> Optional[str]:
        """
        Get application health status
        
        Returns:
            str: One of: Healthy, Progressing, Degraded, Suspended, Missing, Unknown, None
        """
        app = self.get_application(app_name)
        if not app:
            return None
        
        return app.get("status", {}).get("health", {}).get("status", "Unknown")
    
    def wait_for_sync(self, app_name: str, timeout: int = 300) -> bool:
        """
        Wait for application to sync
        
        Args:
            app_name: Application name
            timeout: Timeout in seconds (default: 300)
            
        Returns:
            bool: True if synced successfully
        """
        import time
        
        start = time.time()
        while time.time() - start < timeout:
            status = self.get_application_status(app_name)
            
            if status == "Synced":
                logger.info(f"Application {app_name} synced successfully")
                return True
            elif status is None:
                logger.error(f"Application {app_name} not found")
                return False
            
            time.sleep(5)
        
        logger.error(f"Timeout waiting for {app_name} to sync")
        return False
