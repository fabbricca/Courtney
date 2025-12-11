# GLaDOS Web Interface

Web-based interface for GLaDOS with full voice support and PWA capabilities for mobile.

## Features

- **Text Chat**: Send and receive text messages
- **Voice Input**: Push-to-talk voice input using Web Audio API
- **Voice Output**: TTS audio playback
- **Conversation History**: Load previous messages with infinite scroll
- **PWA Support**: Install as native app on mobile devices
- **Offline Ready**: Service worker caches static assets
- **Wake Lock**: Keep screen awake during conversation (optional)
- **Responsive Design**: Works on desktop and mobile

## Quick Start

### 1. Start the WebSocket Bridge Server

```bash
cd websocket-bridge
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
python bridge_server.py
```

The bridge will listen on `ws://localhost:8765` by default.

### 2. Serve the Web Frontend

Option A: Using Python's built-in server:
```bash
cd web
python3 -m http.server 8080
```

Option B: Using Node.js http-server:
```bash
npm install -g http-server
cd web
http-server -p 8080
```

### 3. Access the Interface

Open your browser and navigate to:
```
http://localhost:8080
```

## Configuration

### Server URL

The default server URL is `ws://localhost:8765`. You can change this in the connection screen before connecting.

For remote access, use:
```
wss://your-domain.com/ws
```

### Authentication

You need a valid GLaDOS JWT authentication token. To obtain a token:

```bash
# Using the admin CLI
cd /path/to/glados
python -m glados.admin create-token --username your-username --role user --days 30
```

## Mobile Installation (PWA)

### Android (Chrome/Edge)

1. Open the web interface in Chrome or Edge
2. Tap the menu button (⋮)
3. Select "Add to Home screen" or "Install app"
4. Follow the prompts

The app will be installed with an icon on your home screen and will run in standalone mode (no browser UI).

### iOS (Safari)

1. Open the web interface in Safari
2. Tap the Share button
3. Select "Add to Home Screen"
4. Name the app and tap "Add"

Note: iOS has more restrictions on PWAs, particularly around background operation and notifications.

## Audio Permissions

### Microphone Access

The first time you click the voice button, your browser will request microphone permission. Click "Allow" to enable voice input.

If you accidentally denied permission:

**Chrome/Edge:**
1. Click the lock icon in the address bar
2. Find "Microphone" in permissions
3. Change to "Allow"
4. Reload the page

**Firefox:**
1. Click the lock icon in the address bar
2. Click "Connection secure"
3. Click "More information"
4. Go to "Permissions" tab
5. Uncheck "Use default" for Microphone
6. Select "Allow"
7. Reload the page

## Troubleshooting

### Connection Issues

**"Failed to connect to WebSocket":**
- Check that the bridge server is running
- Verify the server URL is correct
- Check firewall settings
- For WSS (HTTPS), ensure valid TLS certificate

**"Authentication failed":**
- Verify your token is valid and not expired
- Check that the GLaDOS server is running
- Check the bridge server logs for details

### Audio Issues

**Microphone not working:**
- Grant microphone permission in browser
- Check that no other app is using the microphone
- Try a different browser
- Check browser console for errors

**No audio playback:**
- Check browser volume/mute settings
- Check that audio is enabled in settings
- Click anywhere on the page first (autoplay policy)
- Check browser console for errors

**High latency:**
- Check network connection quality
- Use wired connection instead of WiFi if possible
- Close other bandwidth-intensive applications

### Mobile Issues

**App closes in background:**
- This is expected behavior on most mobile browsers
- Enable "Keep screen awake" in settings to prevent device sleep
- On Android, disable battery optimization for the browser

**App not installing (PWA):**
- Ensure using HTTPS (not HTTP)
- Clear browser cache and try again
- Check that manifest.json is accessible
- Some browsers don't support PWA installation

## Development

### File Structure

```
web/
├── index.html           # Main HTML page
├── manifest.json        # PWA manifest
├── service-worker.js    # Service worker for offline support
├── css/
│   └── style.css        # Stylesheet
├── js/
│   ├── app.js          # Main application logic
│   ├── websocket.js    # WebSocket connection manager
│   └── audio.js        # Audio capture and playback
├── icons/
│   ├── icon-192.png    # PWA icon (192x192)
│   └── icon-512.png    # PWA icon (512x512)
└── README.md           # This file
```

### Customization

**Colors and Theme:**
Edit CSS variables in `css/style.css`:
```css
:root {
    --primary-color: #ff6600;  /* Change this */
    --background: #000000;      /* And this */
    ...
}
```

**WebSocket Configuration:**
Edit constants in `websocket-bridge/bridge_server.py`:
```python
GLADOS_HOST = '10.0.0.15'  # GLaDOS server IP
GLADOS_PORT = 5555          # GLaDOS server port
WEBSOCKET_PORT = 8765       # Bridge listen port
```

## Security Considerations

1. **Use HTTPS/WSS in production** - Required for PWA and microphone access
2. **Keep tokens secure** - Don't share tokens or commit them to git
3. **Rotate tokens regularly** - Set reasonable expiry times
4. **Use strong authentication** - Ensure GLaDOS server has proper auth
5. **Review CORS settings** - Configure bridge server appropriately

## Performance

**Recommended Browser Requirements:**
- Chrome 90+ / Edge 90+
- Firefox 88+
- Safari 14+ (limited PWA support)

**Network Requirements:**
- Minimum 1 Mbps for text only
- 5+ Mbps recommended for voice
- Low latency (<100ms) for best voice experience

**Device Requirements:**
- Modern smartphone (2019+)
- 2GB+ RAM
- Microphone and speakers/headphones

## License

See main GLaDOS project license.

## Support

For issues, see: https://github.com/your-repo/glados/issues
