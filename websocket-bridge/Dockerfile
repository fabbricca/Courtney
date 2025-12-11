FROM python:3.11-slim

LABEL maintainer="GLaDOS Team"
LABEL description="WebSocket Bridge Server for GLaDOS"

# Set working directory
WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY bridge_server.py .
COPY protocol.py .

# Expose WebSocket port
EXPOSE 8765

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV GLADOS_HOST=10.0.0.15
ENV GLADOS_PORT=5555
ENV WEBSOCKET_HOST=0.0.0.0
ENV WEBSOCKET_PORT=8765

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import socket; s = socket.socket(); s.connect(('localhost', 8765)); s.close()" || exit 1

# Run the bridge server
CMD ["python", "bridge_server.py"]
