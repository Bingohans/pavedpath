"""
Kubernetes client for pod deployment and management
Handles all interactions with Kubernetes API
"""

from kubernetes import client, config
from kubernetes.client.rest import ApiException
from typing import Dict, Any, List, Optional
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class KubernetesClient:
    """
    Kubernetes API client with security-hardened pod deployment
    """
    
    def __init__(self):
        """Initialize Kubernetes client"""
        try:
            # Try to load in-cluster config first (when running in K8s)
            config.load_incluster_config()
            logger.info("Loaded in-cluster Kubernetes config")
        except config.ConfigException:
            try:
                # Fall back to kubeconfig file (for local development)
                config.load_kube_config()
                logger.info("Loaded Kubernetes config from kubeconfig")
            except config.ConfigException as e:
                logger.error(f"Failed to load Kubernetes config: {str(e)}")
                raise
        
        self.v1 = client.CoreV1Api()
        self.apps_v1 = client.AppsV1Api()
        logger.info("Kubernetes client initialized successfully")
    
    def check_health(self) -> bool:
        """Check if Kubernetes API is accessible"""
        try:
            self.v1.get_api_resources()
            return True
        except Exception as e:
            logger.error(f"Kubernetes health check failed: {str(e)}")
            return False
    
    def deploy_pod(self, validated_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Deploy a pod with security hardening
        
        Args:
            validated_data: Validated deployment configuration
            
        Returns:
            Deployment result information
            
        Raises:
            ApiException: If deployment fails
        """
        pod_name = validated_data['pod_name']
        namespace = validated_data['namespace']
        
        logger.info(f"Deploying pod {pod_name} to namespace {namespace}")
        
        try:
            # 1. Ensure namespace exists
            self._ensure_namespace_exists(namespace)
            
            # 2. Create pod specification
            pod_spec = self._build_pod_spec(validated_data)
            
            # 3. Deploy pod
            pod = self.v1.create_namespaced_pod(
                namespace=namespace,
                body=pod_spec
            )
            
            logger.info(f"Successfully created pod: {pod_name}")
            
            # 4. Create service for the pod
            service = self._create_service(validated_data)
            logger.info(f"Successfully created service for pod: {pod_name}")
            
            # 5. Create PVC if storage requested
            if validated_data['has_storage']:
                pvc = self._create_pvc(validated_data)
                logger.info(f"Successfully created PVC for pod: {pod_name}")
            
            # 6. Create secret if database requested
            if validated_data['has_database']:
                secret = self._create_database_secret(validated_data)
                logger.info(f"Successfully created secret for pod: {pod_name}")
            
            return {
                "pod_name": pod_name,
                "namespace": namespace,
                "status": "created",
                "uid": pod.metadata.uid
            }
            
        except ApiException as e:
            logger.error(f"Kubernetes API error: {e.status} - {e.reason}")
            raise
        except Exception as e:
            logger.error(f"Deployment error: {str(e)}")
            raise
    
    def _build_pod_spec(self, validated_data: Dict[str, Any]) -> client.V1Pod:
        """
        Build security-hardened pod specification
        
        Security features:
        - Non-root user
        - Read-only root filesystem
        - Drop all capabilities
        - No privilege escalation
        - Seccomp profile
        """
        resources = validated_data['resources']
        
        # Container specification
        container = client.V1Container(
            name=f"{validated_data['pod_name']}-container",
            image=validated_data['docker_image'],
            
            # Resource limits
            resources=client.V1ResourceRequirements(
                requests={
                    "memory": f"{resources['memory_request_mb']}Mi",
                    "cpu": f"{resources['cpu_request_m']}m"
                },
                limits={
                    "memory": f"{resources['memory_limit_mb']}Mi",
                    "cpu": f"{resources['cpu_limit_m']}m"
                }
            ),
            
            # Security context
            security_context=client.V1SecurityContext(
                allow_privilege_escalation=False,
                read_only_root_filesystem=True,
                run_as_non_root=True,
                run_as_user=1000,
                capabilities=client.V1Capabilities(
                    drop=["ALL"]
                )
            ),
            
            # Volume mounts
            volume_mounts=self._build_volume_mounts(validated_data),
            
            # Environment variables
            env=self._build_env_vars(validated_data)
        )
        
        # Pod specification
        pod_spec = client.V1PodSpec(
            containers=[container],
            
            # Pod-level security context
            security_context=client.V1PodSecurityContext(
                run_as_non_root=True,
                run_as_user=1000,
                fs_group=1000,
                seccomp_profile=client.V1SeccompProfile(
                    type="RuntimeDefault"
                )
            ),
            
            # Volumes
            volumes=self._build_volumes(validated_data),
            
            # Restart policy
            restart_policy="Always"
        )
        
        # Pod metadata
        metadata = client.V1ObjectMeta(
            name=validated_data['pod_name'],
            namespace=validated_data['namespace'],
            labels=validated_data['labels'],
            annotations={
                "created-by": "paved-roads-api",
                "created-at": datetime.utcnow().isoformat(),
                "demo": "true",
                "auto-cleanup": "true"
            }
        )
        
        return client.V1Pod(
            api_version="v1",
            kind="Pod",
            metadata=metadata,
            spec=pod_spec
        )
    
    def _build_volume_mounts(self, validated_data: Dict[str, Any]) -> List:
        """Build volume mounts for container"""
        mounts = [
            # Temporary directory (required for read-only root filesystem)
            client.V1VolumeMount(
                name="tmp",
                mount_path="/tmp"
            )
        ]
        
        if validated_data['has_storage']:
            mounts.append(
                client.V1VolumeMount(
                    name="data",
                    mount_path="/data"
                )
            )
        
        return mounts
    
    def _build_volumes(self, validated_data: Dict[str, Any]) -> List:
        """Build volumes for pod"""
        volumes = [
            # Temporary directory volume
            client.V1Volume(
                name="tmp",
                empty_dir=client.V1EmptyDirVolumeSource()
            )
        ]
        
        if validated_data['has_storage']:
            volumes.append(
                client.V1Volume(
                    name="data",
                    persistent_volume_claim=client.V1PersistentVolumeClaimVolumeSource(
                        claim_name=f"{validated_data['pod_name']}-pvc"
                    )
                )
            )
        
        return volumes
    
    def _build_env_vars(self, validated_data: Dict[str, Any]) -> List:
        """Build environment variables for container"""
        env_vars = [
            client.V1EnvVar(name="ENVIRONMENT", value="demo"),
            client.V1EnvVar(name="POD_NAME", value_from=client.V1EnvVarSource(
                field_ref=client.V1ObjectFieldSelector(field_path="metadata.name")
            )),
            client.V1EnvVar(name="POD_NAMESPACE", value_from=client.V1EnvVarSource(
                field_ref=client.V1ObjectFieldSelector(field_path="metadata.namespace")
            ))
        ]
        
        if validated_data['has_database']:
            # Add database environment variables from secret
            secret_name = f"{validated_data['pod_name']}-db-secret"
            env_vars.extend([
                client.V1EnvVar(
                    name="DB_HOST",
                    value_from=client.V1EnvVarSource(
                        secret_key_ref=client.V1SecretKeySelector(
                            name=secret_name,
                            key="host"
                        )
                    )
                ),
                client.V1EnvVar(
                    name="DB_PORT",
                    value_from=client.V1EnvVarSource(
                        secret_key_ref=client.V1SecretKeySelector(
                            name=secret_name,
                            key="port"
                        )
                    )
                ),
                client.V1EnvVar(
                    name="DB_NAME",
                    value_from=client.V1EnvVarSource(
                        secret_key_ref=client.V1SecretKeySelector(
                            name=secret_name,
                            key="database"
                        )
                    )
                )
            ])
        
        return env_vars
    
    def _create_service(self, validated_data: Dict[str, Any]) -> client.V1Service:
        """Create a service for the pod"""
        service_name = validated_data['pod_name']
        namespace = validated_data['namespace']
        
        service = client.V1Service(
            api_version="v1",
            kind="Service",
            metadata=client.V1ObjectMeta(
                name=service_name,
                namespace=namespace,
                labels=validated_data['labels']
            ),
            spec=client.V1ServiceSpec(
                selector={"app": validated_data['pod_name']},
                ports=[
                    client.V1ServicePort(
                        port=80,
                        target_port=8080,
                        protocol="TCP"
                    )
                ],
                type="ClusterIP"
            )
        )
        
        return self.v1.create_namespaced_service(
            namespace=namespace,
            body=service
        )
    
    def _create_pvc(self, validated_data: Dict[str, Any]) -> client.V1PersistentVolumeClaim:
        """Create persistent volume claim"""
        pvc_name = f"{validated_data['pod_name']}-pvc"
        namespace = validated_data['namespace']
        
        pvc = client.V1PersistentVolumeClaim(
            api_version="v1",
            kind="PersistentVolumeClaim",
            metadata=client.V1ObjectMeta(
                name=pvc_name,
                namespace=namespace,
                labels=validated_data['labels']
            ),
            spec=client.V1PersistentVolumeClaimSpec(
                access_modes=["ReadWriteOnce"],
                resources=client.V1ResourceRequirements(
                    requests={"storage": f"{validated_data['storage_gb']}Gi"}
                )
            )
        )
        
        return self.v1.create_namespaced_persistent_volume_claim(
            namespace=namespace,
            body=pvc
        )
    
    def _create_database_secret(self, validated_data: Dict[str, Any]) -> client.V1Secret:
        """Create secret with database credentials"""
        import base64
        
        secret_name = f"{validated_data['pod_name']}-db-secret"
        namespace = validated_data['namespace']
        
        # Demo database credentials (in production, these would come from a vault)
        secret_data = {
            "host": base64.b64encode(b"postgres-service").decode(),
            "port": base64.b64encode(b"5432").decode(),
            "database": base64.b64encode(f"{validated_data['pod_name']}_db".encode()).decode(),
            "username": base64.b64encode(b"demo_user").decode(),
            "password": base64.b64encode(b"demo_password").decode()
        }
        
        secret = client.V1Secret(
            api_version="v1",
            kind="Secret",
            metadata=client.V1ObjectMeta(
                name=secret_name,
                namespace=namespace,
                labels=validated_data['labels']
            ),
            type="Opaque",
            data=secret_data
        )
        
        return self.v1.create_namespaced_secret(
            namespace=namespace,
            body=secret
        )
    
    def _ensure_namespace_exists(self, namespace: str):
        """Ensure namespace exists, create if it doesn't"""
        try:
            self.v1.read_namespace(name=namespace)
        except ApiException as e:
            if e.status == 404:
                logger.info(f"Creating namespace: {namespace}")
                ns = client.V1Namespace(
                    metadata=client.V1ObjectMeta(name=namespace)
                )
                self.v1.create_namespace(body=ns)
            else:
                raise
    
    def pod_exists(self, pod_name: str, namespace: str) -> bool:
        """Check if pod already exists"""
        try:
            self.v1.read_namespaced_pod(name=pod_name, namespace=namespace)
            return True
        except ApiException as e:
            if e.status == 404:
                return False
            raise
    
    def get_pod_status(self, pod_name: str, namespace: str) -> Optional[Dict]:
        """Get pod status information"""
        try:
            pod = self.v1.read_namespaced_pod(name=pod_name, namespace=namespace)
            
            return {
                "name": pod.metadata.name,
                "namespace": pod.metadata.namespace,
                "status": pod.status.phase,
                "ready": f"{sum(c.ready for c in pod.status.container_statuses or [])}/{len(pod.spec.containers)}",
                "restarts": sum(c.restart_count for c in pod.status.container_statuses or []),
                "age": str(datetime.utcnow() - pod.metadata.creation_timestamp.replace(tzinfo=None)),
                "node": pod.spec.node_name,
                "ip": pod.status.pod_ip
            }
        except ApiException as e:
            if e.status == 404:
                return None
            raise
    
    def delete_pod(self, pod_name: str, namespace: str) -> bool:
        """Delete pod and associated resources"""
        try:
            # Delete pod
            self.v1.delete_namespaced_pod(name=pod_name, namespace=namespace)
            logger.info(f"Deleted pod: {pod_name}")
            
            # Delete service
            try:
                self.v1.delete_namespaced_service(name=pod_name, namespace=namespace)
                logger.info(f"Deleted service: {pod_name}")
            except ApiException:
                pass
            
            # Delete PVC
            try:
                self.v1.delete_namespaced_persistent_volume_claim(
                    name=f"{pod_name}-pvc",
                    namespace=namespace
                )
                logger.info(f"Deleted PVC: {pod_name}-pvc")
            except ApiException:
                pass
            
            # Delete secret
            try:
                self.v1.delete_namespaced_secret(
                    name=f"{pod_name}-db-secret",
                    namespace=namespace
                )
                logger.info(f"Deleted secret: {pod_name}-db-secret")
            except ApiException:
                pass
            
            return True
            
        except ApiException as e:
            if e.status == 404:
                return False
            logger.error(f"Failed to delete pod: {str(e)}")
            raise
    
    def list_pods(self, namespaces: List[str]) -> List[Dict]:
        """List all pods in specified namespaces"""
        pods = []
        
        for namespace in namespaces:
            try:
                pod_list = self.v1.list_namespaced_pod(
                    namespace=namespace,
                    label_selector="managed-by=paved-roads"
                )
                
                for pod in pod_list.items:
                    pods.append({
                        "name": pod.metadata.name,
                        "namespace": pod.metadata.namespace,
                        "status": pod.status.phase,
                        "created": pod.metadata.creation_timestamp.isoformat()
                    })
            except ApiException:
                continue
        
        return pods
    
    def close(self):
        """Cleanup resources"""
        logger.info("Closing Kubernetes client")
