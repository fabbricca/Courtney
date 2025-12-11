#!/usr/bin/env python3
"""
WebSocket Bridge Server for GLaDOS

This server acts as a bridge between WebSocket clients (browsers) and
the GLaDOS TCP server. It translates between WebSocket JSON messages
and GLaDOS binary protocol.

Architecture:
    Browser (WebSocket/JSON) <-> Bridge Server <-> GLaDOS Server (TCP/Binary)
"""

import asyncio
import websockets
import json
import logging
import signal
import sys
from typing import Optional
from aiohttp import web
from protocol import ws_to_glados, glados_to_ws, read_glados_message

# Configuration
GLADOS_HOST = '10.0.0.15'
GLADOS_PORT = 5555
WEBSOCKET_HOST = '0.0.0.0'
WEBSOCKET_PORT = 8765
HEALTH_CHECK_PORT = 8766

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('bridge')


class BridgeSession:
    """Manages a single WebSocket<->TCP bridge session."""

    def __init__(self, websocket, client_ip: str):
        self.websocket = websocket
        self.client_ip = client_ip
        self.tcp_reader: Optional[asyncio.StreamReader] = None
        self.tcp_writer: Optional[asyncio.StreamWriter] = None
        self.authenticated = False
        self.user_id = None
        self.username = None

    async def connect_to_glados(self) -> bool:
        """
        Establish TCP connection to GLaDOS server.

        Returns:
            True if connection successful, False otherwise
        """
        try:
            self.tcp_reader, self.tcp_writer = await asyncio.open_connection(
                GLADOS_HOST,
                GLADOS_PORT
            )
            logger.info(f"[{self.client_ip}] TCP connection established to GLaDOS")
            return True
        except Exception as e:
            logger.error(f"[{self.client_ip}] Failed to connect to GLaDOS: {e}")
            return False

    async def ws_to_tcp_forwarder(self):
        """Forward messages from WebSocket to TCP."""
        try:
            async for message in self.websocket:
                try:
                    # Parse JSON message from WebSocket
                    json_msg = json.loads(message)
                    logger.debug(f"[{self.client_ip}] WS->TCP: {json_msg.get('type')}")

                    # Convert to GLaDOS binary protocol
                    binary_msg = ws_to_glados(json_msg)

                    # Send to GLaDOS
                    self.tcp_writer.write(binary_msg)
                    await self.tcp_writer.drain()

                except json.JSONDecodeError as e:
                    logger.error(f"[{self.client_ip}] Invalid JSON: {e}")
                    await self.send_error("Invalid JSON format")

                except ValueError as e:
                    logger.error(f"[{self.client_ip}] Protocol error: {e}")
                    await self.send_error(str(e))

        except websockets.exceptions.ConnectionClosed:
            logger.info(f"[{self.client_ip}] WebSocket connection closed")
        except Exception as e:
            logger.error(f"[{self.client_ip}] WS->TCP error: {e}")

    async def tcp_to_ws_forwarder(self):
        """Forward messages from TCP to WebSocket."""
        try:
            while True:
                # Read one complete message from GLaDOS
                binary_msg = await read_glados_message(self.tcp_reader)
                if not binary_msg:
                    logger.info(f"[{self.client_ip}] TCP connection closed by GLaDOS")
                    break

                try:
                    # Convert to WebSocket JSON
                    json_msg = glados_to_ws(binary_msg)
                    logger.debug(f"[{self.client_ip}] TCP->WS: {json_msg.get('type')}")

                    # Handle auth response
                    if json_msg['type'] == 'auth_response':
                        if json_msg.get('status') == 'ok':
                            self.authenticated = True
                            self.user_id = json_msg.get('user_id')
                            self.username = json_msg.get('username')
                            logger.info(
                                f"[{self.client_ip}] Authenticated as "
                                f"{self.username} (user_id: {self.user_id})"
                            )
                        else:
                            logger.warning(
                                f"[{self.client_ip}] Authentication failed: "
                                f"{json_msg.get('message')}"
                            )

                    # Send to WebSocket
                    await self.websocket.send(json.dumps(json_msg))

                except ValueError as e:
                    logger.error(f"[{self.client_ip}] Protocol error: {e}")
                    await self.send_error(str(e))

        except ConnectionError as e:
            logger.error(f"[{self.client_ip}] TCP connection error: {e}")
        except Exception as e:
            logger.error(f"[{self.client_ip}] TCP->WS error: {e}")

    async def send_error(self, message: str):
        """Send error message to WebSocket client."""
        try:
            error_msg = {
                'type': 'error',
                'message': message
            }
            await self.websocket.send(json.dumps(error_msg))
        except Exception as e:
            logger.error(f"[{self.client_ip}] Failed to send error: {e}")

    async def cleanup(self):
        """Clean up resources."""
        if self.tcp_writer:
            try:
                self.tcp_writer.close()
                await self.tcp_writer.wait_closed()
            except Exception as e:
                logger.error(f"[{self.client_ip}] Error closing TCP connection: {e}")

        logger.info(f"[{self.client_ip}] Session cleaned up")


async def bridge_handler(websocket, path):
    """
    Handle a new WebSocket connection.

    Args:
        websocket: WebSocket connection
        path: Request path (unused)
    """
    client_ip = websocket.remote_address[0]
    logger.info(f"[{client_ip}] New WebSocket connection")

    session = BridgeSession(websocket, client_ip)

    try:
        # Connect to GLaDOS server
        if not await session.connect_to_glados():
            await session.send_error("Failed to connect to GLaDOS server")
            return

        # Run bidirectional forwarding concurrently
        await asyncio.gather(
            session.ws_to_tcp_forwarder(),
            session.tcp_to_ws_forwarder()
        )

    except Exception as e:
        logger.error(f"[{client_ip}] Session error: {e}")

    finally:
        await session.cleanup()


# Health check endpoint handlers
async def health_check(request):
    """Health check endpoint."""
    return web.json_response({
        'status': 'healthy',
        'service': 'glados-websocket-bridge',
        'glados_server': f'{GLADOS_HOST}:{GLADOS_PORT}'
    })


async def ready_check(request):
    """Readiness check endpoint."""
    # Test connection to GLaDOS server
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(GLADOS_HOST, GLADOS_PORT),
            timeout=2.0
        )
        writer.close()
        await writer.wait_closed()

        return web.json_response({
            'status': 'ready',
            'glados_server': 'connected'
        })
    except Exception as e:
        return web.json_response({
            'status': 'not_ready',
            'glados_server': 'disconnected',
            'error': str(e)
        }, status=503)


async def metrics_endpoint(request):
    """Basic metrics endpoint."""
    # This could be extended with prometheus metrics
    return web.json_response({
        'service': 'glados-websocket-bridge',
        'active_connections': 0,  # Would need to track this
        'total_messages': 0  # Would need to track this
    })


async def start_health_server():
    """Start health check HTTP server."""
    app = web.Application()
    app.router.add_get('/health', health_check)
    app.router.add_get('/ready', ready_check)
    app.router.add_get('/metrics', metrics_endpoint)

    runner = web.AppRunner(app)
    await runner.setup()

    site = web.TCPSite(runner, WEBSOCKET_HOST, HEALTH_CHECK_PORT)
    await site.start()

    logger.info(f"Health check server running on {WEBSOCKET_HOST}:{HEALTH_CHECK_PORT}")

    return runner


async def main():
    """Main entry point."""
    logger.info(f"Starting GLaDOS WebSocket Bridge Server")
    logger.info(f"WebSocket: {WEBSOCKET_HOST}:{WEBSOCKET_PORT}")
    logger.info(f"GLaDOS: {GLADOS_HOST}:{GLADOS_PORT}")

    # Handle shutdown signals
    loop = asyncio.get_running_loop()
    stop = loop.create_future()

    def signal_handler(signum, frame):
        logger.info(f"Received signal {signum}, shutting down...")
        if not stop.done():
            stop.set_result(None)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Start health check server
    health_runner = await start_health_server()

    # Start WebSocket server
    async with websockets.serve(bridge_handler, WEBSOCKET_HOST, WEBSOCKET_PORT):
        logger.info("WebSocket bridge server is running")
        logger.info("Press Ctrl+C to stop")

        # Wait for stop signal
        await stop

    # Cleanup health server
    await health_runner.cleanup()

    logger.info("Server stopped")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Server stopped by user")
        sys.exit(0)
