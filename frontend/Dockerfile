# Frontend Dockerfile
FROM nginx:alpine

# Copy static files
COPY index.html /usr/share/nginx/html/index.html
COPY deployment-progress.html /usr/share/nginx/html/deployment-progress.html
COPY config.js /usr/share/nginx/html/config.js
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Copy nginx configuration
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Expose port
EXPOSE 80

# Health check
HEALTHCHECK --interval=30s --timeout=3s \
    CMD wget --quiet --tries=1 --spider http://localhost/ || exit 1
