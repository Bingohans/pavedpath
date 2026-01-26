import logging
from datetime import datetime
from typing import Dict, Optional

from github import Github, GithubException

logger = logging.getLogger(__name__)


class GitHubClient:
    """Manages GitHub repository creation and manifest generation"""

    def __init__(self, token: str, org_name: Optional[str] = None):
        """
        Initialize GitHub client

        Args:
            token: GitHub Personal Access Token
            org_name: Optional organization name (uses user repos if None)
        """
        self.client = Github(token)
        self.org_name = org_name

        # Get organization or user
        if org_name:
            try:
                self.org = self.client.get_organization(org_name)
                logger.info(f"Using GitHub organization: {org_name}")
            except GithubException as e:
                logger.error(f"Failed to get organization {org_name}: {e}")
                raise
        else:
            self.user = self.client.get_user()
            logger.info(f"Using GitHub user: {self.user.login}")

    def create_deployment_repo(
        self,
        pod_name: str,
        namespace: str,
        docker_image: str,
        has_storage: bool,
        has_database: bool,
        resources: Optional[Dict] = None
    ) -> str:
        """
        Create GitHub repository with Kubernetes manifests
        
        Returns:
            str: Repository HTML URL
        """
        repo_name = f"{namespace}-{pod_name}"
        
        logger.info(f"Creating GitHub repo: {repo_name}")
        
        try:
            # Create repository
            if self.org_name:
                repo = self.org.create_repo(
                    name=repo_name,
                    description=f"Kubernetes deployment for {pod_name} in {namespace}",
                    private=False,
                    auto_init=True
                )
            else:
                repo = self.user.create_repo(
                    name=repo_name,
                    description=f"Kubernetes deployment for {pod_name} in {namespace}",
                    private=False,
                    auto_init=True
                )
            
            logger.info(f"Repository created: {repo.html_url}")
            
        except GithubException as e:
            if e.status == 422 and "already exists" in str(e):
                logger.warning(f"Repository {repo_name} already exists, using existing repo")
                
                if self.org_name:
                    repo = self.org.get_repo(repo_name)
                else:
                    repo = self.user.get_repo(repo_name)
                
                logger.info(f"Using existing repository: {repo.html_url}")
            else:
                logger.error(f"Failed to create repository: {e}")
                raise
        
        # Generate manifests
        manifests = self._generate_manifests(
            pod_name=pod_name,
            namespace=namespace,
            docker_image=docker_image,
            has_storage=has_storage,
            has_database=has_database,
            resources=resources
            storage_gb=10
        )
        
        # Push manifests
        for filename, content in manifests.items():
            try:
                try:
                    existing_file = repo.get_contents(f"k8s/{filename}", ref="main")
                    repo.update_file(
                        path=f"k8s/{filename}",
                        message=f"Update {filename}",
                        content=content,
                        sha=existing_file.sha,
                        branch="main"
                    )
                    logger.info(f"Updated file: k8s/{filename}")
                except GithubException:
                    repo.create_file(
                        path=f"k8s/{filename}",
                        message=f"Add {filename}",
                        content=content,
                        branch="main"
                    )
                    logger.info(f"Created file: k8s/{filename}")
                    
            except GithubException as e:
                logger.error(f"Failed to create/update {filename}: {e}")
        
        # Create README
        try:
            readme_content = self._generate_readme(pod_name, namespace, docker_image)
            try:
                existing_readme = repo.get_contents("README.md", ref="main")
                repo.update_file(
                    path="README.md",
                    message="Update README",
                    content=readme_content,
                    sha=existing_readme.sha,
                    branch="main"
                )
            except GithubException:
                repo.create_file(
                    path="README.md",
                    message="Add README",
                    content=readme_content,
                    branch="main"
                )
        except GithubException as e:
            logger.error(f"Failed to create README: {e}")
        
        return repo.html_url

    def _generate_manifests(
        self,
        pod_name: str,
        namespace: str,
        docker_image: str,
        has_storage: bool,
        has_database: bool,
        resources: Optional[Dict] = None
        storage_gb: int = 10
    ) -> Dict[str, str]:
        """Generate Kubernetes manifest files"""

        manifests = {}

        # Default resource limits
        if resources:
            resources = resources
        else:
            resources = {
                "memory_request_mb": 256,
                "memory_limit_mb": 512,
                "cpu_request_m": 100,
                "cpu_limit_m": 500
            }


        # 1. Namespace
        manifests["namespace.yaml"] = f"""---
apiVersion: v1
kind: Namespace
metadata:
  name: {namespace}
  labels:
    created-by: paved-roads
    created-at: "{datetime.utcnow().isoformat()}Z"
"""

        # 2. Deployment
        volume_mounts = []
        volumes = []

        if has_storage:
            volume_mounts.append("""        - name: data
          mountPath: /data""")
            volumes.append(
                """      - name: data
        persistentVolumeClaim:
          claimName: {}-data""".format(pod_name)
            )

        if has_database:
            volume_mounts.append("""        - name: db-secret
          mountPath: /etc/secrets
          readOnly: true""")
            volumes.append(
                """      - name: db-secret
        secret:
          secretName: {}-db-credentials""".format(pod_name)
            )

        volume_mounts_str = (
            "\n".join(volume_mounts) if volume_mounts else "        # No volumes"
        )
        volumes_str = "\n".join(volumes) if volumes else "      # No volumes"

        manifests["deployment.yaml"] = f"""---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: {pod_name}
  namespace: {namespace}
  labels:
    app: {pod_name}
    created-by: paved-roads
spec:
  replicas: 1
  selector:
    matchLabels:
      app: {pod_name}
  template:
    metadata:
      labels:
        app: {pod_name}
    spec:
      securityContext:
        runAsNonRoot: true
        runAsUser: 1000
        fsGroup: 1000
        seccompProfile:
          type: RuntimeDefault
      
      containers:
      - name: app
        image: {docker_image}
        imagePullPolicy: Always
        
        ports:
        - containerPort: 8080
          name: http
          protocol: TCP
        
        resources:
          requests:
            memory: "{resources["memory_request_mb"]}Mi"
            cpu: "{resources["cpu_request_m"]}m"
          limits:
            memory: "{resources["memory_limit_mb"]}Mi"
            cpu: "{resources["cpu_limit_m"]}m"
        
        securityContext:
          allowPrivilegeEscalation: false
          readOnlyRootFilesystem: true
          capabilities:
            drop:
            - ALL
        
        volumeMounts:
        - name: tmp
          mountPath: /tmp
{volume_mounts_str}
      
      volumes:
      - name: tmp
        emptyDir: {{}}
{volumes_str}
"""

        # 3. Service
        manifests["service.yaml"] = f"""---
apiVersion: v1
kind: Service
metadata:
  name: {pod_name}
  namespace: {namespace}
  labels:
    app: {pod_name}
spec:
  type: ClusterIP
  ports:
  - port: 80
    targetPort: 8080
    protocol: TCP
    name: http
  selector:
    app: {pod_name}
"""

        # 4. PVC (if storage requested)
        if has_storage:
            manifests["pvc.yaml"] = f"""---
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: {pod_name}-data
  namespace: {namespace}
  labels:
    app: {pod_name}
spec:
  accessModes:
    - ReadWriteOnce
  storageClassName: rook-ceph-block
  resources:
    requests:
      storage: {storage_gb}Gi
"""

        # 5. Secret (if database requested)
        if has_database:
            manifests["secret.yaml"] = f"""---
apiVersion: v1
kind: Secret
metadata:
  name: {pod_name}-db-credentials
  namespace: {namespace}
  labels:
    app: {pod_name}
type: Opaque
stringData:
  DB_HOST: "postgres.default.svc.cluster.local"
  DB_PORT: "5432"
  DB_NAME: "{pod_name}_db"
  DB_USER: "{pod_name}_user"
  DB_PASSWORD: "CHANGE_ME_IN_PRODUCTION"
"""

        return manifests

    def _generate_readme(self, pod_name: str, namespace: str, docker_image: str) -> str:
        """Generate README for the repository"""

        return f"""# {pod_name}

Kubernetes deployment managed by Paved Roads platform.

## Details

- **Namespace**: `{namespace}`
- **Pod Name**: `{pod_name}`
- **Image**: `{docker_image}`
- **Created**: {datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")} UTC

## Structure

```
k8s/
├── namespace.yaml    - Namespace definition
├── deployment.yaml   - Pod deployment
├── service.yaml      - Service exposure
├── pvc.yaml         - Persistent storage (if applicable)
└── secret.yaml      - Database credentials (if applicable)
```

## Deployment

This repository is automatically deployed to Kubernetes via ArgoCD.

### Manual Deployment

```bash
kubectl apply -f k8s/
```

### Check Status

```bash
kubectl get all -n {namespace}
kubectl logs -n {namespace} deployment/{pod_name}
```

## Cleanup

**Note**: This deployment has auto-cleanup enabled. It will be automatically removed after 5 minutes.

To manually delete:

```bash
kubectl delete namespace {namespace}
```

---

*Generated by Paved Roads - Kubernetes Self-Service Platform*
"""

    def delete_repo(self, repo_name: str) -> bool:
        """Delete a repository"""
        try:
            if self.org_name:
                repo = self.org.get_repo(repo_name)
            else:
                repo = self.user.get_repo(repo_name)

            repo.delete()
            logger.info(f"Deleted repository: {repo_name}")
            return True

        except GithubException as e:
            logger.error(f"Failed to delete repo {repo_name}: {e}")
            return False
