# GLaDOS K8s TCP Proxy

A minimal TCP proxy that forwards connections from your K8s cluster (via NEWT tunnel) to an external GPU server running GLaDOS.

## Architecture

```
┌─────────────┐     NEWT      ┌──────────────┐     TCP      ┌────────────────┐
│   Client    │ ────────────► │  K8s Proxy   │ ───────────► │   GPU Server   │
│  (Browser/  │    Tunnel     │  (this app)  │    Forward   │   (GLaDOS +    │
│   App)      │               │              │              │    RVC +       │
└─────────────┘               └──────────────┘              │    Ollama)     │
                                                            └────────────────┘
```

## Quick Start

### 1. Build the Docker Image

```bash
cd k8s-proxy

# Build locally
docker build -t glados-proxy:latest .

# Or if you have a registry
docker build -t your-registry/glados-proxy:latest .
docker push your-registry/glados-proxy:latest
```

### 2. Configure the GPU Server IP

Edit `k8s-manifests.yaml` and update the ConfigMap with your GPU server's IP:

```yaml
data:
  GLADOS_TARGET: "YOUR_GPU_SERVER_IP:5555"
```

### 3. Deploy to Kubernetes

```bash
# If using a registry, update the image in the deployment first
kubectl apply -f k8s-manifests.yaml

# Check deployment status
kubectl -n glados get pods
kubectl -n glados logs -f deployment/glados-proxy
```

### 4. Set Up NEWT Tunnel

Point your NEWT tunnel to the K8s service:

```bash
# The service is available at: glados-proxy.glados.svc.cluster.local:5555
# Or via NodePort if enabled: <any-node-ip>:30555
```

## Local Testing

Run the proxy locally without K8s:

```bash
# Build
go build -o glados-proxy .

# Run
./glados-proxy -target 192.168.1.100:5555 -listen :5555

# Or using environment variable
GLADOS_TARGET=192.168.1.100:5555 ./glados-proxy
```

## Configuration

| Flag | Env Var | Default | Description |
|------|---------|---------|-------------|
| `-target` | `GLADOS_TARGET` | (required) | GPU server address (e.g., `192.168.1.100:5555`) |
| `-listen` | - | `:5555` | Address to listen on |
| `-timeout` | - | `10s` | Connection timeout |
| `-buffer` | - | `32768` | Buffer size for data transfer |

## GPU Server Setup

On your GPU server, run:

```bash
cd /path/to/GLaDOS
./scripts/start_gpu_server.sh
```

This starts:
- Ollama (LLM) on port 11434
- RVC (voice cloning) on port 5050
- GLaDOS (main app) on port 5555

## Resource Usage

The proxy is extremely lightweight:
- Memory: ~10-20 MB
- CPU: < 1% under normal load
- Binary size: ~6 MB (statically compiled)

## Troubleshooting

### Connection refused
- Verify the GPU server is running and accessible
- Check firewall rules on the GPU server
- Test connectivity: `nc -zv GPU_SERVER_IP 5555`

### Slow connections
- This is likely due to RVC processing, not the proxy
- The proxy adds < 1ms latency

### View proxy logs
```bash
kubectl -n glados logs -f deployment/glados-proxy
```
