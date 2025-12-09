#!/usr/bin/env python3
"""
GLaDOS Terminal Client

A terminal-based client that supports both text and voice input.
Press Enter to send text, or just speak if your mic is unmuted.

Usage:
    python glados_terminal_client.py --server localhost:5555
"""

import argparse
import socket
import struct
import sys
import threading
import subprocess
import select
from collections import deque

import numpy as np

try:
    import sounddevice as sd
except ImportError:
    print("Error: sounddevice not installed. Run: pip install sounddevice")
    sys.exit(1)


# Audio settings
LOCAL_SAMPLE_RATE = 48000
SERVER_SAMPLE_RATE = 16000
CHUNK_MS = 32
LOCAL_CHUNK_SAMPLES = int(LOCAL_SAMPLE_RATE * CHUNK_MS / 1000)

# Protocol constants
TEXT_MESSAGE_MARKER = 0xFFFFFFFF
ASSISTANT_TEXT_MARKER = 0xFFFFFFFE
USER_TRANSCRIPTION_MARKER = 0xFFFFFFFD


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


class GLaDOSTerminalClient:
    """Terminal-based GLaDOS client with text and voice support."""

    def __init__(self, server_host: str, server_port: int):
        self.server_host = server_host
        self.server_port = server_port
        
        self.socket = None
        self.running = False
        
        # Audio playback
        self.playback_queue = deque()
        self.playback_lock = threading.Lock()
        
        # Mic mute detection
        self.mic_detector = MicMuteDetector()
        self.recording_enabled = False
        self.input_stream = None
        
        # Threads
        self.receive_thread = None
        self.playback_thread = None
        self.mic_check_thread = None
        self.input_thread = None

    def connect(self) -> bool:
        """Connect to the GLaDOS server."""
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.connect((self.server_host, self.server_port))
            self.socket.settimeout(0.1)
            print(f"\n✓ Connected to GLaDOS at {self.server_host}:{self.server_port}")
            return True
        except Exception as e:
            print(f"✗ Failed to connect: {e}")
            return False

    def send_text_message(self, text: str):
        """Send a text message to the server."""
        if not self.socket or not text.strip():
            return
        
        # Protocol: [0xFFFFFFFF][length][utf-8 text]
        text_bytes = text.encode('utf-8')
        header = struct.pack("<II", TEXT_MESSAGE_MARKER, len(text_bytes))
        
        try:
            self.socket.sendall(header + text_bytes)
            print(f"\033[94mYou:\033[0m {text}")
        except Exception as e:
            print(f"✗ Failed to send: {e}")

    def _audio_input_callback(self, indata, frames, time, status):
        """Callback for audio input."""
        if not self.recording_enabled or not self.socket or not self.running:
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
                except Exception as e:
                    print(f"Playback error: {e}")
            else:
                _time.sleep(0.05)

    def _receive_loop(self):
        """Receive audio and text from server."""
        buffer = b""
        
        while self.running:
            try:
                data = self.socket.recv(65536)
                if not data:
                    print("\n✗ Disconnected from server")
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
                        print(f"\n\033[94mYou (voice):\033[0m {text}")
                        continue
                    
                    # Check for assistant text message from server
                    if length == ASSISTANT_TEXT_MARKER:
                        text_length = second_field
                        if len(buffer) < 8 + text_length:
                            break
                        text_bytes = buffer[8:8 + text_length]
                        buffer = buffer[8 + text_length:]
                        
                        text = text_bytes.decode('utf-8', errors='replace')
                        print(f"\033[93mGLaDOS:\033[0m {text}")
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
            except Exception as e:
                print(f"\n✗ Receive error: {e}")
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
                if is_muted:
                    self.recording_enabled = False
                    if self.input_stream:
                        self.input_stream.stop()
                    print("\r\033[91m🔇 Mic muted\033[0m - Type message and press Enter, or unmute to speak", end="", flush=True)
                else:
                    self.recording_enabled = True
                    if self.input_stream:
                        self.input_stream.start()
                    print("\r\033[92m🎤 Recording\033[0m - Speak now, or type and press Enter              ", end="", flush=True)
            
            _time.sleep(0.2)

    def _input_loop(self):
        """Handle keyboard input."""
        # Deprecated: Input is now handled in the main thread
        pass

    def run(self):
        """Main entry point."""
        print("\n" + "="*50)
        print("        GLaDOS Terminal Client")
        print("="*50)
        print("Commands: Type text + Enter | 'quit' to exit")
        print("Voice: Unmute your mic to speak")
        print("="*50 + "\n")
        
        if not self.connect():
            return
        
        self.running = True
        
        # Start threads
        self.receive_thread = threading.Thread(target=self._receive_loop, daemon=True)
        self.receive_thread.start()
        
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
        except Exception as e:
            print(f"Audio input error: {e}")
        
        # Start mic check thread
        self.mic_check_thread = threading.Thread(target=self._mic_check_loop, daemon=True)
        self.mic_check_thread.start()
        
        # Main input loop (runs in main thread)
        print("\r\033[91m🔇 Mic muted\033[0m - Type message and press Enter, or unmute to speak", end="", flush=True)
        try:
            while self.running:
                try:
                    # Use select for non-blocking input on Linux
                    if select.select([sys.stdin], [], [], 0.1)[0]:
                        line = sys.stdin.readline()
                        if line:
                            text = line.strip()
                            if text:
                                if text.lower() in ('quit', 'exit', 'q'):
                                    print("\nExiting...")
                                    self.running = False
                                    break
                                self.send_text_message(text)
                except Exception:
                    pass
        except KeyboardInterrupt:
            pass
        
        print("\n\nShutting down...")
        self.running = False
        
        if self.input_stream:
            self.input_stream.close()
        if self.socket:
            self.socket.close()


def main():
    parser = argparse.ArgumentParser(description="GLaDOS Terminal Client")
    parser.add_argument(
        "--server",
        default="localhost:5555",
        help="Server address (host:port)"
    )
    args = parser.parse_args()
    
    # Parse server address
    if ":" in args.server:
        host, port = args.server.rsplit(":", 1)
        port = int(port)
    else:
        host = args.server
        port = 5555
    
    client = GLaDOSTerminalClient(host, port)
    client.run()


if __name__ == "__main__":
    main()
