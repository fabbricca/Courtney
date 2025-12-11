"""
Protocol translation between WebSocket JSON and GLaDOS binary protocol.

GLaDOS Binary Protocol:
    [marker: uint32 big-endian][length: uint32 big-endian][data: bytes]

Markers:
    0xFFFFFFFF - TEXT_FROM_CLIENT
    0xFFFFFFFE - TEXT_TO_CLIENT
    0xFFFFFFFD - AUTH_TOKEN_FROM_CLIENT
    0xFFFFFFFC - AUTH_RESPONSE_TO_CLIENT
    0xFFFFFFFB - HISTORY_REQUEST_FROM_CLIENT
    0xFFFFFFFA - HISTORY_RESPONSE_TO_CLIENT
    0xFFFFFFF9 - AUDIO_FROM_CLIENT (new)
    0xFFFFFFF8 - AUDIO_TO_CLIENT (new)
"""

import struct
import json
import base64
import asyncio
from typing import Optional

# Protocol markers
TEXT_FROM_CLIENT = 0xFFFFFFFF
TEXT_TO_CLIENT = 0xFFFFFFFE
AUTH_TOKEN_FROM_CLIENT = 0xFFFFFFFD
AUTH_RESPONSE_TO_CLIENT = 0xFFFFFFFC
HISTORY_REQUEST_FROM_CLIENT = 0xFFFFFFFB
HISTORY_RESPONSE_TO_CLIENT = 0xFFFFFFFA
AUDIO_FROM_CLIENT = 0xFFFFFFF9
AUDIO_TO_CLIENT = 0xFFFFFFF8


def ws_to_glados(msg: dict) -> bytes:
    """
    Convert WebSocket JSON message to GLaDOS binary protocol.

    Args:
        msg: Dictionary with 'type' and message-specific fields

    Returns:
        Binary data in GLaDOS protocol format

    Raises:
        ValueError: If message type is unknown or required fields missing
    """
    msg_type = msg.get('type')

    if msg_type == 'auth':
        marker = AUTH_TOKEN_FROM_CLIENT
        token = msg.get('token', '')
        data = token.encode('utf-8')

    elif msg_type == 'text':
        marker = TEXT_FROM_CLIENT
        message = msg.get('message', '')
        data = message.encode('utf-8')

    elif msg_type == 'audio':
        marker = AUDIO_FROM_CLIENT
        # Audio data is base64 encoded in JSON
        audio_b64 = msg.get('data', '')
        audio_bytes = base64.b64decode(audio_b64)

        # Pack metadata + audio
        metadata = {
            'format': msg.get('format', 'pcm_s16le'),
            'sample_rate': msg.get('sampleRate', 16000)
        }
        metadata_json = json.dumps(metadata).encode('utf-8')
        metadata_length = len(metadata_json)

        # [metadata_length:4][metadata:N][audio:M]
        data = struct.pack('>I', metadata_length) + metadata_json + audio_bytes

    elif msg_type == 'history_request':
        marker = HISTORY_REQUEST_FROM_CLIENT
        request_data = {
            'offset': msg.get('offset', 0),
            'limit': msg.get('limit', 50)
        }
        data = json.dumps(request_data).encode('utf-8')

    else:
        raise ValueError(f"Unknown message type: {msg_type}")

    # Pack: [marker:4][length:4][data:N]
    return struct.pack('>I', marker) + struct.pack('>I', len(data)) + data


def glados_to_ws(binary_data: bytes) -> dict:
    """
    Convert GLaDOS binary protocol to WebSocket JSON message.

    Args:
        binary_data: Binary data in GLaDOS protocol format

    Returns:
        Dictionary with 'type' and message-specific fields

    Raises:
        ValueError: If binary data is malformed or marker is unknown
    """
    if len(binary_data) < 8:
        raise ValueError("Binary data too short (need at least 8 bytes for header)")

    marker = struct.unpack('>I', binary_data[0:4])[0]
    length = struct.unpack('>I', binary_data[4:8])[0]
    data = binary_data[8:8+length]

    if len(data) != length:
        raise ValueError(f"Data length mismatch: expected {length}, got {len(data)}")

    if marker == AUTH_RESPONSE_TO_CLIENT:
        # Auth response is JSON
        response_data = json.loads(data.decode('utf-8'))
        return {
            'type': 'auth_response',
            **response_data
        }

    elif marker == TEXT_TO_CLIENT:
        # Text response
        return {
            'type': 'text',
            'message': data.decode('utf-8')
        }

    elif marker == AUDIO_TO_CLIENT:
        # Audio response - extract metadata and audio
        if len(data) < 4:
            raise ValueError("Audio data too short")

        metadata_length = struct.unpack('>I', data[0:4])[0]
        metadata_json = data[4:4+metadata_length]
        audio_bytes = data[4+metadata_length:]

        metadata = json.loads(metadata_json.decode('utf-8'))

        return {
            'type': 'audio',
            'format': metadata.get('format', 'wav'),
            'data': base64.b64encode(audio_bytes).decode('ascii')
        }

    elif marker == HISTORY_RESPONSE_TO_CLIENT:
        # History response is JSON
        history_data = json.loads(data.decode('utf-8'))
        return {
            'type': 'history_response',
            **history_data
        }

    else:
        raise ValueError(f"Unknown marker: 0x{marker:08X}")


async def read_glados_message(reader: asyncio.StreamReader) -> Optional[bytes]:
    """
    Read one complete message from GLaDOS TCP stream.

    Args:
        reader: AsyncIO stream reader

    Returns:
        Complete binary message including header, or None if connection closed

    Raises:
        ConnectionError: If connection is closed unexpectedly
    """
    # Read header (marker + length)
    header = await reader.read(8)
    if not header:
        return None

    if len(header) < 8:
        raise ConnectionError("Connection closed while reading header")

    marker = struct.unpack('>I', header[0:4])[0]
    length = struct.unpack('>I', header[4:8])[0]

    # Read data
    data = await reader.readexactly(length)

    # Return complete message
    return header + data
