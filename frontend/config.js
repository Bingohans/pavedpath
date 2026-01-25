// API Configuration
const API_CONFIG = {
    // Change this to your actual API URL when deploying
    BASE_URL: window.ENV?.API_BASE_URL || 'http://localhost:8000',

    ENDPOINTS: {
        HEALTH: '/api/health',
        GET_TOKEN: '/api/demo/token',
        DEPLOY: '/api/deploy',
        GET_STATUS: '/api/deployment',
        DELETE: '/api/deployment',
        LIST: '/api/deployments'
    }
};

// Get full API URL
function getApiUrl(endpoint) {
    return `${API_CONFIG.BASE_URL}${endpoint}`;
}

// API client with error handling
class ApiClient {
    constructor() {
        this.token = null;
    }

    async getToken() {
        try {
            const response = await fetch(getApiUrl(API_CONFIG.ENDPOINTS.GET_TOKEN), {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                }
            });

            if (!response.ok) {
                throw new Error(`Failed to get token: ${response.status}`);
            }

            const data = await response.json();
            this.token = data.token;
            return this.token;
        } catch (error) {
            console.error('Token error:', error);
            throw error;
        }
    }

    async deploy(deploymentData) {
        if (!this.token) {
            await this.getToken();
        }

        try {
            const response = await fetch(getApiUrl(API_CONFIG.ENDPOINTS.DEPLOY), {
                method: 'POST',
                headers: {
                    'Authorization': `Bearer ${this.token}`,
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(deploymentData)
            });

            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.detail || `Deployment failed: ${response.status}`);
            }

            return await response.json();
        } catch (error) {
            console.error('Deployment error:', error);
            throw error;
        }
    }

    async getStatus(namespace, podName) {
        if (!this.token) {
            await this.getToken();
        }

        try {
            const response = await fetch(
                getApiUrl(`${API_CONFIG.ENDPOINTS.GET_STATUS}/${namespace}/${podName}`),
                {
                    headers: {
                        'Authorization': `Bearer ${this.token}`
                    }
                }
            );

            if (!response.ok) {
                throw new Error(`Failed to get status: ${response.status}`);
            }

            return await response.json();
        } catch (error) {
            console.error('Status error:', error);
            throw error;
        }
    }

    async deleteDeployment(namespace, podName) {
        if (!this.token) {
            await this.getToken();
        }

        try {
            const response = await fetch(
                getApiUrl(`${API_CONFIG.ENDPOINTS.DELETE}/${namespace}/${podName}`),
                {
                    method: 'DELETE',
                    headers: {
                        'Authorization': `Bearer ${this.token}`
                    }
                }
            );

            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.detail || `Delete failed: ${response.status}`);
            }

            return await response.json();
        } catch (error) {
            console.error('Delete error:', error);
            throw error;
        }
    }

    async checkHealth() {
        try {
            const response = await fetch(getApiUrl(API_CONFIG.ENDPOINTS.HEALTH));
            return response.ok;
        } catch (error) {
            console.error('Health check error:', error);
            return false;
        }
    }
}

// Export for use in HTML files
window.ApiClient = ApiClient;
window.API_CONFIG = API_CONFIG;
