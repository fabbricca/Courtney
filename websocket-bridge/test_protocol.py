"""
Unit tests for WebSocket<->GLaDOS protocol translation.
"""

import pytest
import struct
import json
import base64
from protocol import (
    ws_to_glados,
    glados_to_ws,
    TEXT_FROM_CLIENT,
    TEXT_TO_CLIENT,
    AUTH_TOKEN_FROM_CLIENT,
    AUTH_RESPONSE_TO_CLIENT,
    HISTORY_REQUEST_FROM_CLIENT,
    HISTORY_RESPONSE_TO_CLIENT,
    AUDIO_FROM_CLIENT,
    AUDIO_TO_CLIENT
)


class TestWSToGLaDOS:
    """Test WebSocket JSON to GLaDOS binary conversion."""

    def test_auth_message(self):
        """Test authentication message conversion."""
        msg = {
            'type': 'auth',
            'token': 'test-token-12345'
        }

        binary = ws_to_glados(msg)

        # Check marker
        marker = struct.unpack('>I', binary[0:4])[0]
        assert marker == AUTH_TOKEN_FROM_CLIENT

        # Check length
        length = struct.unpack('>I', binary[4:8])[0]
        assert length == len('test-token-12345')

        # Check data
        data = binary[8:8+length].decode('utf-8')
        assert data == 'test-token-12345'

    def test_text_message(self):
        """Test text message conversion."""
        msg = {
            'type': 'text',
            'message': 'Hello GLaDOS'
        }

        binary = ws_to_glados(msg)

        marker = struct.unpack('>I', binary[0:4])[0]
        assert marker == TEXT_FROM_CLIENT

        length = struct.unpack('>I', binary[4:8])[0]
        assert length == len('Hello GLaDOS')

        data = binary[8:8+length].decode('utf-8')
        assert data == 'Hello GLaDOS'

    def test_audio_message(self):
        """Test audio message conversion."""
        # Create test audio data
        test_audio = b'\x00\x01\x02\x03\x04\x05'
        audio_b64 = base64.b64encode(test_audio).decode('ascii')

        msg = {
            'type': 'audio',
            'data': audio_b64,
            'format': 'pcm_s16le',
            'sampleRate': 16000
        }

        binary = ws_to_glados(msg)

        marker = struct.unpack('>I', binary[0:4])[0]
        assert marker == AUDIO_FROM_CLIENT

        # Extract metadata length
        metadata_length = struct.unpack('>I', binary[8:12])[0]

        # Extract metadata
        metadata_json = binary[12:12+metadata_length]
        metadata = json.loads(metadata_json.decode('utf-8'))

        assert metadata['format'] == 'pcm_s16le'
        assert metadata['sample_rate'] == 16000

        # Extract audio
        audio_data = binary[12+metadata_length:]
        assert audio_data == test_audio

    def test_history_request(self):
        """Test history request conversion."""
        msg = {
            'type': 'history_request',
            'offset': 10,
            'limit': 25
        }

        binary = ws_to_glados(msg)

        marker = struct.unpack('>I', binary[0:4])[0]
        assert marker == HISTORY_REQUEST_FROM_CLIENT

        length = struct.unpack('>I', binary[4:8])[0]
        data = binary[8:8+length].decode('utf-8')

        request_data = json.loads(data)
        assert request_data['offset'] == 10
        assert request_data['limit'] == 25

    def test_unknown_message_type(self):
        """Test that unknown message type raises error."""
        msg = {
            'type': 'invalid_type',
            'data': 'test'
        }

        with pytest.raises(ValueError, match="Unknown message type"):
            ws_to_glados(msg)

    def test_empty_text_message(self):
        """Test empty text message."""
        msg = {
            'type': 'text',
            'message': ''
        }

        binary = ws_to_glados(msg)

        length = struct.unpack('>I', binary[4:8])[0]
        assert length == 0

    def test_unicode_text_message(self):
        """Test text message with unicode characters."""
        msg = {
            'type': 'text',
            'message': 'Hello 世界 🌍'
        }

        binary = ws_to_glados(msg)

        length = struct.unpack('>I', binary[4:8])[0]
        data = binary[8:8+length].decode('utf-8')
        assert data == 'Hello 世界 🌍'


class TestGLaDOSToWS:
    """Test GLaDOS binary to WebSocket JSON conversion."""

    def test_auth_response_success(self):
        """Test successful authentication response."""
        response_data = {
            'status': 'ok',
            'user_id': 123,
            'username': 'alice'
        }
        response_json = json.dumps(response_data).encode('utf-8')

        binary = (
            struct.pack('>I', AUTH_RESPONSE_TO_CLIENT) +
            struct.pack('>I', len(response_json)) +
            response_json
        )

        result = glados_to_ws(binary)

        assert result['type'] == 'auth_response'
        assert result['status'] == 'ok'
        assert result['user_id'] == 123
        assert result['username'] == 'alice'

    def test_auth_response_failure(self):
        """Test failed authentication response."""
        response_data = {
            'status': 'error',
            'message': 'Invalid token'
        }
        response_json = json.dumps(response_data).encode('utf-8')

        binary = (
            struct.pack('>I', AUTH_RESPONSE_TO_CLIENT) +
            struct.pack('>I', len(response_json)) +
            response_json
        )

        result = glados_to_ws(binary)

        assert result['type'] == 'auth_response'
        assert result['status'] == 'error'
        assert result['message'] == 'Invalid token'

    def test_text_response(self):
        """Test text response."""
        text = "I'm afraid I can't do that."

        binary = (
            struct.pack('>I', TEXT_TO_CLIENT) +
            struct.pack('>I', len(text)) +
            text.encode('utf-8')
        )

        result = glados_to_ws(binary)

        assert result['type'] == 'text'
        assert result['message'] == text

    def test_audio_response(self):
        """Test audio response."""
        test_audio = b'\xFF\xFE\xFD\xFC\xFB\xFA'

        metadata = {
            'format': 'wav',
            'sample_rate': 22050
        }
        metadata_json = json.dumps(metadata).encode('utf-8')

        data = struct.pack('>I', len(metadata_json)) + metadata_json + test_audio

        binary = (
            struct.pack('>I', AUDIO_TO_CLIENT) +
            struct.pack('>I', len(data)) +
            data
        )

        result = glados_to_ws(binary)

        assert result['type'] == 'audio'
        assert result['format'] == 'wav'

        audio_decoded = base64.b64decode(result['data'])
        assert audio_decoded == test_audio

    def test_history_response(self):
        """Test history response."""
        history_data = {
            'messages': [
                {'role': 'user', 'content': 'Hello', 'timestamp': '2024-12-11T10:00:00Z'},
                {'role': 'assistant', 'content': 'Hi!', 'timestamp': '2024-12-11T10:00:01Z'}
            ],
            'has_more': True
        }
        history_json = json.dumps(history_data).encode('utf-8')

        binary = (
            struct.pack('>I', HISTORY_RESPONSE_TO_CLIENT) +
            struct.pack('>I', len(history_json)) +
            history_json
        )

        result = glados_to_ws(binary)

        assert result['type'] == 'history_response'
        assert len(result['messages']) == 2
        assert result['has_more'] is True
        assert result['messages'][0]['role'] == 'user'

    def test_malformed_binary_too_short(self):
        """Test that malformed binary (too short) raises error."""
        binary = b'\x00\x00\x00\x01'  # Only 4 bytes

        with pytest.raises(ValueError, match="Binary data too short"):
            glados_to_ws(binary)

    def test_malformed_binary_length_mismatch(self):
        """Test that length mismatch raises error."""
        binary = (
            struct.pack('>I', TEXT_TO_CLIENT) +
            struct.pack('>I', 100) +  # Says 100 bytes
            b'short'  # But only 5 bytes
        )

        with pytest.raises(ValueError, match="Data length mismatch"):
            glados_to_ws(binary)

    def test_unknown_marker(self):
        """Test that unknown marker raises error."""
        binary = (
            struct.pack('>I', 0x12345678) +  # Invalid marker
            struct.pack('>I', 4) +
            b'test'
        )

        with pytest.raises(ValueError, match="Unknown marker"):
            glados_to_ws(binary)

    def test_unicode_text_response(self):
        """Test text response with unicode."""
        text = "Hello 世界 🤖"

        binary = (
            struct.pack('>I', TEXT_TO_CLIENT) +
            struct.pack('>I', len(text.encode('utf-8'))) +
            text.encode('utf-8')
        )

        result = glados_to_ws(binary)

        assert result['type'] == 'text'
        assert result['message'] == text


class TestRoundTrip:
    """Test round-trip conversions."""

    def test_text_roundtrip(self):
        """Test that text survives round-trip conversion."""
        original_text = "Hello GLaDOS, how are you?"

        # Browser -> Bridge
        ws_msg = {'type': 'text', 'message': original_text}
        binary = ws_to_glados(ws_msg)

        # Simulate GLaDOS response
        response_binary = (
            struct.pack('>I', TEXT_TO_CLIENT) +
            struct.pack('>I', len(original_text)) +
            original_text.encode('utf-8')
        )

        # Bridge -> Browser
        result = glados_to_ws(response_binary)

        assert result['message'] == original_text

    def test_auth_roundtrip(self):
        """Test authentication flow."""
        token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.test"

        # Browser sends auth
        ws_msg = {'type': 'auth', 'token': token}
        binary = ws_to_glados(ws_msg)

        # Verify token is in binary
        marker = struct.unpack('>I', binary[0:4])[0]
        assert marker == AUTH_TOKEN_FROM_CLIENT

        # Simulate GLaDOS auth response
        response_data = {'status': 'ok', 'user_id': 1, 'username': 'test'}
        response_json = json.dumps(response_data).encode('utf-8')
        response_binary = (
            struct.pack('>I', AUTH_RESPONSE_TO_CLIENT) +
            struct.pack('>I', len(response_json)) +
            response_json
        )

        # Bridge -> Browser
        result = glados_to_ws(response_binary)

        assert result['type'] == 'auth_response'
        assert result['status'] == 'ok'
        assert result['user_id'] == 1


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
