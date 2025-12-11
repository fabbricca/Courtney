# GLaDOS WebSocket Bridge Server

WebSocket-to-TCP bridge that translates between browser WebSocket connections and GLaDOS's binary TCP protocol.

## Architecture

```
Browser (WebSocket/JSON) <-> Bridge Server <-> GLaDOS Server (TCP/Binary)
```

The bridge server:
- Accepts WebSocket connections from browsers
- Translates JSON messages to GLaDOS binary protocol
- Forwards binary responses back as JSON
- Handles authentication flow
- Manages multiple concurrent sessions

## Installation

```bash
cd websocket-bridge
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

## Configuration

Edit `bridge_server.py` to configure:

```python
GLADOS_HOST = '10.0.0.15'     # GLaDOS server IP address
GLADOS_PORT = 5555             # GLaDOS server port
WEBSOCKET_HOST = '0.0.0.0'     # Interface to listen on
WEBSOCKET_PORT = 8765          # Port to listen on
```

## Usage

### Start the Bridge Server

```bash
python bridge_server.py
```

The server will start and listen for WebSocket connections.

### Connect from Browser

```javascript
const ws = new WebSocket('ws://localhost:8765');

ws.onopen = () => {
    // Send authentication
    ws.send(JSON.stringify({
        type: 'auth',
        token: 'your-jwt-token-here'
    }));
};

ws.onmessage = (event) => {
    const msg = JSON.parse(event.data);
    console.log('Received:', msg);
};

// Send text message
ws.send(JSON.stringify({
    type: 'text',
    message: 'Hello GLaDOS'
}));
```

## Protocol

### WebSocket → GLaDOS (Browser to Server)

**Authentication:**
```json
{
    "type": "auth",
    "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
}
```

**Text Message:**
```json
{
    "type": "text",
    "message": "Hello GLaDOS"
}
```

**Audio Data:**
```json
{
    "type": "audio",
    "format": "pcm_s16le",
    "sampleRate": 16000,
    "data": "base64_encoded_audio..."
}
```

**History Request:**
```json
{
    "type": "history_request",
    "offset": 0,
    "limit": 50
}
```

### GLaDOS → WebSocket (Server to Browser)

**Auth Response:**
```json
{
    "type": "auth_response",
    "status": "ok",
    "user_id": 1,
    "username": "alice"
}
```

**Text Response:**
```json
{
    "type": "text",
    "message": "Hello. How can I assist you?"
}
```

**Audio Response:**
```json
{
    "type": "audio",
    "format": "wav",
    "data": "base64_encoded_audio..."
}
```

**History Response:**
```json
{
    "type": "history_response",
    "messages": [
        {"role": "user", "content": "Hello", "timestamp": "..."},
        {"role": "assistant", "content": "Hi!", "timestamp": "..."}
    ],
    "has_more": true
}
```

**Error:**
```json
{
    "type": "error",
    "message": "Error description"
}
```

## Logging

The bridge server logs all connections, messages, and errors. Logs include:

- Client IP address
- Connection/disconnection events
- Authentication status
- Message types (not content, for privacy)
- Errors and warnings

Example output:
```
2024-12-11 10:30:00 - bridge - INFO - Starting GLaDOS WebSocket Bridge Server
2024-12-11 10:30:00 - bridge - INFO - WebSocket: 0.0.0.0:8765
2024-12-11 10:30:00 - bridge - INFO - GLaDOS: 10.0.0.15:5555
2024-12-11 10:30:00 - bridge - INFO - WebSocket bridge server is running
2024-12-11 10:30:15 - bridge - INFO - [192.168.1.100] New WebSocket connection
2024-12-11 10:30:15 - bridge - INFO - [192.168.1.100] TCP connection established to GLaDOS
2024-12-11 10:30:15 - bridge - INFO - [192.168.1.100] Authenticated as alice (user_id: 1)
```

## Production Deployment

### Using Systemd (Linux)

Create `/etc/systemd/system/glados-bridge.service`:

```ini
[Unit]
Description=GLaDOS WebSocket Bridge
After=network.target

[Service]
Type=simple
User=glados
WorkingDirectory=/path/to/GLaDOS/websocket-bridge
ExecStart=/path/to/GLaDOS/websocket-bridge/venv/bin/python bridge_server.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl enable glados-bridge
sudo systemctl start glados-bridge
sudo systemctl status glados-bridge
```

### Using Docker

See `Dockerfile` in this directory (to be created).

### Behind Reverse Proxy (Nginx)

```nginx
server {
    listen 443 ssl http2;
    server_name glados.yourdomain.com;

    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;

    # WebSocket endpoint
    location /ws {
        proxy_pass http://localhost:8765;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # Timeouts
        proxy_connect_timeout 7d;
        proxy_send_timeout 7d;
        proxy_read_timeout 7d;
    }

    # Static files
    location / {
        root /path/to/GLaDOS/web;
        index index.html;
        try_files $uri $uri/ /index.html;
    }
}
```

## Security

1. **Use WSS (WebSocket Secure) in production** - Encrypt all traffic
2. **Validate tokens** - Bridge forwards tokens to GLaDOS for validation
3. **Rate limiting** - Consider adding rate limits for DOS protection
4. **Firewall** - Only allow connections from expected sources
5. **Monitoring** - Monitor for unusual connection patterns

## Troubleshooting

**Bridge can't connect to GLaDOS:**
- Check GLADOS_HOST and GLADOS_PORT settings
- Verify GLaDOS server is running
- Check firewall rules
- Check network connectivity: `telnet 10.0.0.15 5555`

**Clients can't connect to bridge:**
- Check WEBSOCKET_PORT is not in use: `netstat -an | grep 8765`
- Check firewall allows incoming connections
- Verify correct URL in client (ws:// vs wss://)

**High memory usage:**
- Each client connection uses ~5-10 MB
- Monitor with: `ps aux | grep bridge_server`
- Consider connection limits if needed

**Messages not forwarding:**
- Check bridge logs for protocol errors
- Verify message format matches protocol
- Check both WebSocket and TCP connections are established

## Development

### Running Tests

```bash
python -m pytest tests/
```

### Protocol Translation

See `protocol.py` for implementation details.

Key functions:
- `ws_to_glados(msg: dict) -> bytes` - JSON to binary
- `glados_to_ws(data: bytes) -> dict` - Binary to JSON
- `read_glados_message(reader) -> bytes` - Read complete message

### Adding New Message Types

1. Add marker constant to `protocol.py`
2. Implement encoding in `ws_to_glados()`
3. Implement decoding in `glados_to_ws()`
4. Update documentation

## Performance

**Benchmarks (single connection):**
- Memory: ~10 MB per connection
- CPU: <1% per connection (idle)
- Latency: <5ms protocol translation overhead
- Throughput: Tested up to 100 concurrent connections

## License

See main GLaDOS project license.
