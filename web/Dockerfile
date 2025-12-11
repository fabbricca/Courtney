FROM nginx:alpine

LABEL maintainer="GLaDOS Team"
LABEL description="GLaDOS Web Frontend"

# Copy web files
COPY index.html /usr/share/nginx/html/
COPY manifest.json /usr/share/nginx/html/
COPY service-worker.js /usr/share/nginx/html/
COPY css/ /usr/share/nginx/html/css/
COPY js/ /usr/share/nginx/html/js/
COPY icons/ /usr/share/nginx/html/icons/

# Copy nginx configuration
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Expose HTTP port
EXPOSE 80

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD wget --no-verbose --tries=1 --spider http://localhost/ || exit 1

# nginx starts automatically with the base image
