#!/usr/bin/env python3
"""
GLaDOS Network Client (Core Logic)

Extracted networking logic from terminal client for reuse.
Handles socket connection, audio streaming, and protocol.
"""

import socket
import struct
import threading
import subprocess
from collections import deque
from typing import Callable, Optional
from pathlib import Path

import numpy as np
import sounddevice as sd

# Optional authentication support
try:
    from client_auth import ClientAuthHelper
    AUTH_AVAILABLE = True
except ImportError:
    AUTH_AVAILABLE = False
    ClientAuthHelper = None  # type: ignore


# Audio settings
LOCAL_SAMPLE_RATE = 48000
SERVER_SAMPLE_RATE = 16000
CHUNK_MS = 32
LOCAL_CHUNK_SAMPLES = int(LOCAL_SAMPLE_RATE * CHUNK_MS / 1000)

# Protocol constants
TEXT_MESSAGE_MARKER = 0xFFFFFFFF
ASSISTANT_TEXT_MARKER = 0xFFFFFFFE
USER_TRANSCRIPTION_MARKER = 0xFFFFFFFD
KEEPALIVE_MARKER = 0xFFFFFFFC


class MicMuteDetector:
    """Detects if the microphone is muted at the system level."""

    def is_muted(self) -> bool:
        """Check if mic is muted using pactl (PipeWire/PulseAudio)."""
        try:
            result = subprocess.run(
                ["pactl", "get-source-mute", "@DEFAULT_SOURCE@"],
                capture_output=True,
                text=True,
                timeout=0.5
            )
            return "yes" in result.stdout.lower()
        except Exception:
            return False


class GLaDOSNetworkClient:
    """
    Core networking client for GLaDOS.

    Handles:
    - Socket connection and protocol
    - Audio streaming (input/output)
    - Text messaging
    - Mic mute detection

    UI-agnostic: callbacks for all events.
    """

    def __init__(
        self,
        server_host: str,
        server_port: int,
        on_user_text: Optional[Callable[[str], None]] = None,
        on_user_voice: Optional[Callable[[str], None]] = None,
        on_assistant_text: Optional[Callable[[str], None]] = None,
        on_connection_status: Optional[Callable[[bool], None]] = None,
        on_mic_status: Optional[Callable[[bool], None]] = None,
        auth_token: Optional[str] = None,
        auth_token_file: Optional[Path] = None,
    ):
        """
        Initialize network client.

        Args:
            server_host: Server hostname/IP
            server_port: Server port
            on_user_text: Callback for user text messages (text)
            on_user_voice: Callback for user voice transcriptions (text)
            on_assistant_text: Callback for assistant messages (text)
            on_connection_status: Callback for connection status (connected: bool)
            on_mic_status: Callback for mic mute status (is_muted: bool)
            auth_token: JWT token for authentication (optional, v2.1+)
            auth_token_file: Path to file containing JWT token (optional, v2.1+)
        """
        self.server_host = server_host
        self.server_port = server_port

        # Callbacks
        self.on_user_text = on_user_text
        self.on_user_voice = on_user_voice
        self.on_assistant_text = on_assistant_text
        self.on_connection_status = on_connection_status
        self.on_mic_status = on_mic_status

        # Connection state
        self.socket: Optional[socket.socket] = None
        self.running = False
        self.connected = False

        # Audio playback
        self.playback_queue = deque()
        self.playback_lock = threading.Lock()

        # Mic mute detection
        self.mic_detector = MicMuteDetector()
        self.recording_enabled = False
        self.input_stream: Optional[sd.InputStream] = None

        # Threads
        self.receive_thread: Optional[threading.Thread] = None
        self.playback_thread: Optional[threading.Thread] = None
        self.mic_check_thread: Optional[threading.Thread] = None
        self.keepalive_thread: Optional[threading.Thread] = None

        # Authentication (v2.1+)
        self.auth_token = auth_token
        if AUTH_AVAILABLE and ClientAuthHelper is not None:
            self.auth_helper = ClientAuthHelper(auth_token_file)
        else:
            self.auth_helper = None

    def connect(self) -> bool:
        """
        Connect to the GLaDOS server.

        If authentication is configured, performs JWT handshake before
        returning. The socket timeout is temporarily increased during
        authentication, then restored to 0.1s for normal operation.

        Returns:
            True if connected (and authenticated if required), False otherwise
        """
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.connect((self.server_host, self.server_port))

            # Perform authentication if token available
            if self.auth_helper or self.auth_token:
                # Use longer timeout for auth handshake
                self.socket.settimeout(10.0)

                token = self.auth_token
                if not token and self.auth_helper:
                    token = self.auth_helper.get_token()

                if token and self.auth_helper:
                    auth_success = self.auth_helper.authenticate_connection(
                        self.socket, token
                    )
                    if not auth_success:
                        # Authentication failed
                        self.socket.close()
                        self.connected = False
                        if self.on_connection_status:
                            self.on_connection_status(False)
                        return False

            # Restore normal timeout for audio/text streaming
            self.socket.settimeout(0.1)
            self.connected = True

            if self.on_connection_status:
                self.on_connection_status(True)

            return True

        except Exception as e:
            self.connected = False
            if self.on_connection_status:
                self.on_connection_status(False)
            return False

    def send_text_message(self, text: str) -> bool:
        """
        Send a text message to the server.

        Args:
            text: Message text

        Returns:
            True if sent successfully
        """
        if not self.socket or not self.connected or not text.strip():
            return False

        try:
            # Protocol: [0xFFFFFFFF][length][utf-8 text]
            text_bytes = text.encode('utf-8')
            header = struct.pack("<II", TEXT_MESSAGE_MARKER, len(text_bytes))
            self.socket.sendall(header + text_bytes)

            # Notify UI (for echo/display)
            if self.on_user_text:
                self.on_user_text(text)

            return True
        except Exception:
            return False

    def _audio_input_callback(self, indata, frames, time, status):
        """Callback for audio input."""
        if not self.socket or not self.running or not self.connected:
            return

        # If recording is disabled (muted), don't send audio
        if not self.recording_enabled:
            return

        # Resample from 48kHz to 16kHz
        audio_48k = indata[:, 0]
        ratio = SERVER_SAMPLE_RATE / LOCAL_SAMPLE_RATE
        new_len = int(len(audio_48k) * ratio)
        indices = np.linspace(0, len(audio_48k) - 1, new_len)
        audio_16k = np.interp(indices, np.arange(len(audio_48k)), audio_48k).astype(np.float32)

        # Convert to int16
        audio_int16 = (audio_16k * 32767).astype(np.int16)

        try:
            self.socket.sendall(audio_int16.tobytes())
        except:
            pass

    def _playback_loop(self):
        """Play received audio."""
        import time as _time
        while self.running:
            audio = None
            with self.playback_lock:
                if self.playback_queue:
                    audio = self.playback_queue.popleft()

            if audio is not None:
                try:
                    sd.play(audio, LOCAL_SAMPLE_RATE, device="pipewire")
                    sd.wait()
                except Exception:
                    pass
            else:
                _time.sleep(0.05)

    def _receive_loop(self):
        """Receive audio and text from server."""
        buffer = b""

        while self.running:
            try:
                data = self.socket.recv(65536)
                if not data:
                    # Disconnected
                    self.connected = False
                    if self.on_connection_status:
                        self.on_connection_status(False)
                    self.running = False
                    break

                buffer += data

                # Process complete messages
                while len(buffer) >= 8:
                    length, second_field = struct.unpack("<II", buffer[:8])

                    # Check for user transcription (speech-to-text result)
                    if length == USER_TRANSCRIPTION_MARKER:
                        text_length = second_field
                        if len(buffer) < 8 + text_length:
                            break
                        text_bytes = buffer[8:8 + text_length]
                        buffer = buffer[8 + text_length:]

                        text = text_bytes.decode('utf-8', errors='replace')
                        if self.on_user_voice:
                            self.on_user_voice(text)
                        continue

                    # Check for assistant text message from server
                    if length == ASSISTANT_TEXT_MARKER:
                        text_length = second_field
                        if len(buffer) < 8 + text_length:
                            break
                        text_bytes = buffer[8:8 + text_length]
                        buffer = buffer[8 + text_length:]

                        text = text_bytes.decode('utf-8', errors='replace')
                        if self.on_assistant_text:
                            self.on_assistant_text(text)
                        continue

                    # Check for keepalive
                    if length == KEEPALIVE_MARKER:
                        buffer = buffer[8:]
                        continue

                    # Stop playback command
                    if length == 0:
                        with self.playback_lock:
                            self.playback_queue.clear()
                        buffer = buffer[8:]
                        continue

                    # Audio data
                    sample_rate = second_field
                    if len(buffer) < 8 + length:
                        break

                    audio_bytes = buffer[8:8 + length]
                    buffer = buffer[8 + length:]

                    # Convert to float32
                    audio_int16 = np.frombuffer(audio_bytes, dtype=np.int16)
                    audio_float = audio_int16.astype(np.float32) / 32768.0

                    # Resample to local rate
                    if sample_rate != LOCAL_SAMPLE_RATE:
                        ratio = LOCAL_SAMPLE_RATE / sample_rate
                        new_len = int(len(audio_float) * ratio)
                        indices = np.linspace(0, len(audio_float) - 1, new_len)
                        audio_float = np.interp(indices, np.arange(len(audio_float)), audio_float).astype(np.float32)

                    with self.playback_lock:
                        self.playback_queue.append(audio_float)

            except socket.timeout:
                continue
            except Exception:
                self.connected = False
                if self.on_connection_status:
                    self.on_connection_status(False)
                self.running = False
                break

    def _mic_check_loop(self):
        """Periodically check mic mute status and start/stop recording."""
        import time as _time
        last_status = None

        while self.running:
            is_muted = self.mic_detector.is_muted()

            if is_muted != last_status:
                last_status = is_muted

                # Update recording state
                self.recording_enabled = not is_muted

                # Start/stop audio stream
                if self.input_stream:
                    if is_muted:
                        self.input_stream.stop()
                    else:
                        self.input_stream.start()

                # Notify UI
                if self.on_mic_status:
                    self.on_mic_status(is_muted)

            _time.sleep(0.2)

    def _keepalive_loop(self):
        """Send keepalive to prevent connection timeout."""
        import time as _time
        # Send properly sized silence chunks (512 samples = 1024 bytes)
        silence_chunk = np.zeros(512, dtype=np.int16).tobytes()

        while self.running:
            if self.socket and self.connected:
                try:
                    self.socket.sendall(silence_chunk)
                except:
                    pass
            _time.sleep(2.0)

    def start(self) -> bool:
        """
        Start the client (threads, audio streams).

        Returns:
            True if started successfully
        """
        if not self.connected:
            return False

        self.running = True

        # Start receive thread
        self.receive_thread = threading.Thread(target=self._receive_loop, daemon=True)
        self.receive_thread.start()

        # Start playback thread
        self.playback_thread = threading.Thread(target=self._playback_loop, daemon=True)
        self.playback_thread.start()

        # Setup audio input
        try:
            self.input_stream = sd.InputStream(
                samplerate=LOCAL_SAMPLE_RATE,
                channels=1,
                dtype=np.float32,
                blocksize=LOCAL_CHUNK_SAMPLES,
                callback=self._audio_input_callback
            )
        except Exception:
            pass

        # Start mic check thread
        self.mic_check_thread = threading.Thread(target=self._mic_check_loop, daemon=True)
        self.mic_check_thread.start()

        # Start keepalive thread
        self.keepalive_thread = threading.Thread(target=self._keepalive_loop, daemon=True)
        self.keepalive_thread.start()

        return True

    def stop(self):
        """Stop the client and cleanup."""
        self.running = False
        self.connected = False

        if self.input_stream:
            self.input_stream.close()

        if self.socket:
            try:
                self.socket.close()
            except:
                pass

        if self.on_connection_status:
            self.on_connection_status(False)

    def is_connected(self) -> bool:
        """Check if connected to server."""
        return self.connected and self.running

    def is_recording(self) -> bool:
        """Check if microphone is recording (not muted)."""
        return self.recording_enabled
