#!/bin/bash
# setup-secrets.sh - Complete secrets setup for Paved Roads

set -e

echo "🔐 Setting up Kubernetes Secrets for Paved Roads"
echo "=================================================="

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if kubectl is available
if ! command -v kubectl &> /dev/null; then
    echo "❌ kubectl not found. Please install kubectl first."
    exit 1
fi

# Create namespace if it doesn't exist
echo -e "${YELLOW}📦 Creating namespace...${NC}"
kubectl create namespace paved-roads --dry-run=client -o yaml | kubectl apply -f -

# Generate JWT secret
echo -e "${YELLOW}🔑 Generating JWT secret...${NC}"
JWT_SECRET=$(openssl rand -base64 32)

# Create API secrets
echo -e "${YELLOW}📝 Creating API secrets...${NC}"
kubectl create secret generic paved-roads-api-secrets \
  --from-literal=JWT_SECRET_KEY="$JWT_SECRET" \
  --from-literal=LOG_LEVEL="INFO" \
  --from-literal=RATE_LIMIT_PER_HOUR="3" \
  --from-literal=AUTO_CLEANUP_MINUTES="5" \
  --namespace=paved-roads \
  --dry-run=client -o yaml | kubectl apply -f -

echo ""
echo -e "${GREEN}✅ Secrets created successfully!${NC}"
echo ""
echo "=================================================="
echo "⚠️  IMPORTANT: Save this JWT secret securely!"
echo "=================================================="
echo "JWT_SECRET_KEY: $JWT_SECRET"
echo "=================================================="
echo ""
echo "To verify secrets:"
echo "  kubectl get secret paved-roads-api-secrets -n paved-roads"
echo ""
echo "To view secret (base64 encoded):"
echo "  kubectl get secret paved-roads-api-secrets -n paved-roads -o yaml"
echo ""

# Save to file (optional)
read -p "Do you want to save the JWT secret to a file? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "JWT_SECRET_KEY=$JWT_SECRET" > .env.secrets
    echo "✅ Saved to .env.secrets (DO NOT COMMIT THIS FILE!)"
fi

echo ""
echo "🎉 Setup complete!"
