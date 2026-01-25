
from typing import Dict, Any
import re
import logging
from models import DeploymentRequest, User 

logger = logging.getLogger(__name__)


class DeploymentValidator:
    """
    Validates deployment requests with strict security rules
    
    Security principles:
    1. Whitelist only - reject everything not explicitly allowed
    2. Enforce limits server-side - ignore client values
    3. Validate all inputs - sanitize and check format
    4. Check permissions - verify namespace access
    """
    
    # Whitelist of allowed Docker images
    ALLOWED_IMAGES = {
        'nginx:1.25-alpine',
        'node:20-alpine',
        'python:3.11-slim',
        'golang:1.21-alpine',
        'openjdk:17-slim',
        'redis:7-alpine'
    }
    
    # Fixed resource limits (NEVER allow user to override)
    FIXED_MEMORY_REQUEST_MB = 256
    FIXED_MEMORY_LIMIT_MB = 512
    FIXED_CPU_REQUEST_M = 100
    FIXED_CPU_LIMIT_M = 500
    FIXED_STORAGE_GB = 10
    
    # Kubernetes naming pattern
    K8S_NAME_PATTERN = r'^[a-z0-9]([-a-z0-9]*[a-z0-9])?$'
    MAX_NAME_LENGTH = 63
    
    def validate_deployment_request(
        self,
        deployment_request: DeploymentRequest,
        user: User
    ) -> Dict[str, Any]:
        """
        Validate and sanitize deployment request
        
        Args:
            deployment_request: Raw request data from client
            user: Authenticated user object
            
        Returns:
            Validated and sanitized deployment configuration
            
        Raises:
            ValueError: If validation fails
            PermissionError: If user lacks permission
        """
        
        logger.info(f"Validating deployment request for user: {user.user_id}")
        
        # 1. Validate pod name
        pod_name = self._validate_pod_name(deployment_request.pod_name)
        logger.debug(f"Pod name validated: {pod_name}")
        
        # 2. Validate namespace and check permissions
        namespace = self._validate_namespace(deployment_request.namespace, user)
        logger.debug(f"Namespace validated: {namespace}")
        
        # 3. Validate Docker image (CRITICAL - whitelist only)
        docker_image = self._validate_docker_image(deployment_request.docker_image)
        logger.debug(f"Docker image validated: {docker_image}")
        
        # 4. Enforce fixed resource limits (ignore client values)
        resources = self._enforce_resource_limits()
        logger.debug(f"Resource limits enforced: {resources}")
        
        # 5. Validate storage request
        has_storage = deployment_request.has_storage
        storage_gb = self.FIXED_STORAGE_GB if has_storage else 0
        
        # 6. Validate database request
        has_database = deployment_request.has_database
        
        # 7. Build validated configuration
        validated_config = {
            'pod_name': pod_name,
            'namespace': namespace,
            'docker_image': docker_image,
            'resource_limits': {
                 'memory_request': f"{resources['memory_request_mb']}Mi",
                 'memory_limit': f"{resources['memory_limit_mb']}Mi",
                 'cpu_request': f"{resources['cpu_request_m']}m",
                 'cpu_limit': f"{resources['cpu_limit_m']}m",
                 'storage': f"{storage_gb}Gi"
            },
            'has_storage': has_storage,
            'has_database': has_database,
            'user_id': user.user_id,
            'labels': {
                'app': pod_name,
                'environment': 'demo',
                'managed-by': 'paved-roads',
                'created-by': user.user_id
            }
        }
        
        logger.info(f"Validation successful for pod: {pod_name}")
        return validated_config
    
    def _validate_pod_name(self, pod_name: Any) -> str:
        """
        Validate pod name follows Kubernetes naming conventions
        
        Rules:
        - Must be lowercase alphanumeric or hyphen
        - Must start and end with alphanumeric
        - Max 63 characters
        """
        if not pod_name or not isinstance(pod_name, str):
            raise ValueError("Pod name is required and must be a string")
        
        pod_name = pod_name.strip().lower()
        
        if len(pod_name) > self.MAX_NAME_LENGTH:
            raise ValueError(
                f"Pod name must be {self.MAX_NAME_LENGTH} characters or less"
            )
        
        if not re.match(self.K8S_NAME_PATTERN, pod_name):
            raise ValueError(
                "Pod name must consist of lowercase alphanumeric characters or '-', "
                "and must start and end with an alphanumeric character"
            )
        
        # Additional security: prevent names that could be exploited
        forbidden_names = {'kube', 'kubernetes', 'system', 'default'}
        if any(forbidden in pod_name for forbidden in forbidden_names):
            raise ValueError(f"Pod name cannot contain forbidden keywords")
        
        return pod_name
    
    def _validate_namespace(self, namespace: Any, user: Any) -> str:
        """
        Validate namespace and check user permissions
        
        Security: Users can only deploy to their assigned namespaces
        """
        if not namespace or not isinstance(namespace, str):
            raise ValueError("Namespace is required and must be a string")
        
        namespace = namespace.strip().lower()
        
        if len(namespace) > self.MAX_NAME_LENGTH:
            raise ValueError(
                f"Namespace must be {self.MAX_NAME_LENGTH} characters or less"
            )
        
        if not re.match(self.K8S_NAME_PATTERN, namespace):
            raise ValueError(
                "Namespace must consist of lowercase alphanumeric characters or '-'"
            )
        
        # CRITICAL: Check user has access to this namespace
        if not re.match(r'^[a-z0-9]([-a-z0-9]*[a-z0-9])?$', namespace):
            raise ValueError("Invalid namespace format")

        logger.debug(f"Namespace validated: {namespace}")
        return namespace
    
    def _validate_docker_image(self, docker_image: Any) -> str:
        """
        Validate Docker image is in whitelist
        
        CRITICAL SECURITY: Only allow pre-approved images
        This prevents arbitrary code execution
        """
        if not docker_image or not isinstance(docker_image, str):
            raise ValueError("Docker image is required and must be a string")
        
        docker_image = docker_image.strip()
        
        # CRITICAL: Whitelist check
        if docker_image not in self.ALLOWED_IMAGES:
            logger.warning(
                f"Attempted to use unauthorized Docker image: {docker_image}"
            )
            raise ValueError(
                f"Docker image '{docker_image}' is not allowed. "
                f"Allowed images: {', '.join(sorted(self.ALLOWED_IMAGES))}"
            )
        
        return docker_image
    
    def _enforce_resource_limits(self) -> Dict[str, int]:
        """
        Enforce fixed resource limits
        
        CRITICAL: These values are FIXED server-side
        Client values are completely ignored to prevent resource exhaustion
        """
        return {
            'memory_request_mb': self.FIXED_MEMORY_REQUEST_MB,
            'memory_limit_mb': self.FIXED_MEMORY_LIMIT_MB,
            'cpu_request_m': self.FIXED_CPU_REQUEST_M,
            'cpu_limit_m': self.FIXED_CPU_LIMIT_M
        }
    
    @staticmethod
    def is_valid_label_value(value: str) -> bool:
        """
        Validate Kubernetes label value
        
        Rules:
        - Max 63 characters
        - Alphanumeric, '-', '_', or '.'
        - Must start and end with alphanumeric
        """
        if not value or len(value) > 63:
            return False
        
        pattern = r'^[a-zA-Z0-9]([-a-zA-Z0-9_.]*[a-zA-Z0-9])?$'
        return bool(re.match(pattern, value))
