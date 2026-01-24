# Kubernetes Paved Roads API

Secure backend API for simplified Kubernetes pod deployment with built-in validation, security hardening, and automatic cleanup.

## 🔒 Security Features

- **Whitelist-only Docker images** - Prevents arbitrary code execution
- **Server-side validation** - Never trusts client input
- **Fixed resource limits** - Prevents resource exhaustion
- **JWT authentication** - Secure API access
- **Rate limiting** - 3 deployments per hour per user
- **Namespace isolation** - Users can only access assigned namespaces
- **Security hardening** - Non-root containers, capability dropping, read-only filesystem
- **Auto-cleanup** - Demo deployments deleted after 5 minutes

## 📋 Prerequisites

- Python 3.11+
- Kubernetes cluster access
- kubectl configured
- Docker (for containerized deployment)

## 🚀 Quick Start

### Local Development

1. **Clone and setup:**
```bash
cd backend
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

2. **Configure environment:**
```bash
cp .env.example .env
# Edit .env with your settings
```

3. **Run the API:**
```bash
# Development mode with auto-reload
uvicorn main:app --reload --host 0.0.0.0 --port 8000

# Or using the main.py directly
python main.py
```

4. **Access API documentation:**
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

### Docker Deployment

1. **Build image:**
```bash
docker build -t k8s-paved-roads-api:latest .
```

2. **Run container:**
```bash
docker run -d \
  --name paved-roads-api \
  -p 8000:8000 \
  -v ~/.kube/config:/app/.kube/config \
  -e KUBECONFIG_PATH=/app/.kube/config \
  -e JWT_SECRET_KEY=your-secret-key \
  k8s-paved-roads-api:latest
```

### Kubernetes Deployment

1. **Create deployment:**
```bash
kubectl apply -f k8s/deployment.yaml
kubectl apply -f k8s/service.yaml
```

2. **Access via port-forward:**
```bash
kubectl port-forward svc/paved-roads-api 8000:8000
```

## 📚 API Endpoints

### Authentication

**Get Demo Token** (for testing)
```bash
POST /api/demo/token
```

Response:
```json
{
  "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "expires_in": 3600,
  "token_type": "Bearer"
}
```

### Deployment

**Deploy Pod**
```bash
POST /api/deploy
Authorization: Bearer <token>
Content-Type: application/json

{
  "pod_name": "my-app",
  "namespace": "development",
  "docker_image": "nginx:1.25-alpine",
  "has_storage": false,
  "has_database": false
}
```

**Get Deployment Status**
```bash
GET /api/deployment/{namespace}/{pod_name}
Authorization: Bearer <token>
```

**Delete Deployment**
```bash
DELETE /api/deployment/{namespace}/{pod_name}
Authorization: Bearer <token>
```

**List Deployments**
```bash
GET /api/deployments?namespace=development
Authorization: Bearer <token>
```

## 🔐 Security Configuration

### Allowed Docker Images

Edit `validator.py` to add/remove allowed images:

```python
ALLOWED_IMAGES = {
    'nginx:1.25-alpine',
    'node:20-alpine',
    'python:3.11-slim',
    # Add your approved images here
}
```

### Resource Limits

Edit `validator.py` to change fixed limits:

```python
FIXED_MEMORY_REQUEST_MB = 256
FIXED_MEMORY_LIMIT_MB = 512
FIXED_CPU_REQUEST_M = 100
FIXED_CPU_LIMIT_M = 500
```

### JWT Secret

**IMPORTANT:** Always change the default JWT secret in production!

```bash
# Generate a secure secret
python -c "import secrets; print(secrets.token_urlsafe(32))"

# Set in environment
export JWT_SECRET_KEY="your-generated-secret"
```

## 🧪 Testing

### Using cURL

1. **Get token:**
```bash
TOKEN=$(curl -s -X POST http://localhost:8000/api/demo/token | jq -r '.token')
```

2. **Deploy pod:**
```bash
curl -X POST http://localhost:8000/api/deploy \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "pod_name": "test-app",
    "namespace": "development",
    "docker_image": "nginx:1.25-alpine",
    "has_storage": false,
    "has_database": false
  }'
```

3. **Check status:**
```bash
curl http://localhost:8000/api/deployment/development/test-app \
  -H "Authorization: Bearer $TOKEN"
```

4. **Delete:**
```bash
curl -X DELETE http://localhost:8000/api/deployment/development/test-app \
  -H "Authorization: Bearer $TOKEN"
```

### Using Python

```python
import requests

# Get token
response = requests.post("http://localhost:8000/api/demo/token")
token = response.json()["token"]

headers = {"Authorization": f"Bearer {token}"}

# Deploy
deploy_data = {
    "pod_name": "my-app",
    "namespace": "development",
    "docker_image": "nginx:1.25-alpine",
    "has_storage": False,
    "has_database": False
}

response = requests.post(
    "http://localhost:8000/api/deploy",
    json=deploy_data,
    headers=headers
)

print(response.json())
```

## 📊 Monitoring

### Health Check

```bash
curl http://localhost:8000/api/health
```

Response:
```json
{
  "status": "healthy",
  "kubernetes": "connected",
  "timestamp": "2025-01-24T12:00:00Z"
}
```

### Logs

```bash
# Docker
docker logs -f paved-roads-api

# Kubernetes
kubectl logs -f deployment/paved-roads-api
```

## 🔧 Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `JWT_SECRET_KEY` | Secret key for JWT tokens | (required) |
| `JWT_ALGORITHM` | JWT algorithm | HS256 |
| `JWT_EXPIRE_MINUTES` | Token expiration time | 60 |
| `ALLOWED_ORIGINS` | CORS allowed origins | localhost |
| `LOG_LEVEL` | Logging level | INFO |
| `RATE_LIMIT_PER_HOUR` | Max deployments per hour | 3 |
| `AUTO_CLEANUP_MINUTES` | Auto-delete after minutes | 5 |

### RBAC Configuration

The API needs these Kubernetes permissions:

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: paved-roads-deployer
rules:
- apiGroups: [""]
  resources: ["pods", "services", "secrets", "persistentvolumeclaims", "namespaces"]
  verbs: ["get", "list", "create", "delete", "watch"]
```

## 🚨 Troubleshooting

### Cannot connect to Kubernetes

```bash
# Check kubeconfig
kubectl cluster-info

# Verify RBAC permissions
kubectl auth can-i create pods --as=system:serviceaccount:default:paved-roads-api
```

### Rate limit exceeded

Wait for the rate limit window to reset (1 hour) or increase `RATE_LIMIT_PER_HOUR` in configuration.

### Deployment fails

Check logs for detailed error:
```bash
docker logs paved-roads-api --tail=50
```

Common issues:
- Namespace doesn't exist (will be auto-created)
- Pod name already exists (delete old pod first)
- Insufficient cluster resources

## 📝 Production Checklist

- [ ] Change JWT_SECRET_KEY to a secure random value
- [ ] Configure proper CORS origins
- [ ] Set up OAuth/OIDC integration (replace demo tokens)
- [ ] Enable HTTPS/TLS
- [ ] Configure proper RBAC in Kubernetes
- [ ] Set up monitoring and alerting
- [ ] Configure log aggregation
- [ ] Set appropriate rate limits
- [ ] Review and adjust resource limits
- [ ] Implement backup for any persistent data
- [ ] Set up disaster recovery procedures

## 🤝 Contributing

1. Follow security best practices
2. Add tests for new features
3. Update documentation
4. Never commit secrets or credentials

## 📄 License

Internal use only - Paved Roads Project

## 🆘 Support

For issues or questions, contact the Platform Engineering team.
