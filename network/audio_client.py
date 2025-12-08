#!/usr/bin/env python3
"""
GLaDOS Network Audio Client

Thin client that captures audio from your microphone and streams it to
the GLaDOS server, then plays back the TTS audio responses.

Usage:
    python audio_client.py --server 192.168.1.100:5555
"""

import argparse
import socket
import struct
import sys
import threading
from collections import deque

import numpy as np

try:
    import sounddevice as sd
except ImportError:
    print("Error: sounddevice not installed. Run: pip install sounddevice")
    sys.exit(1)


# Audio settings
# Client captures at 48kHz (PipeWire default), resamples to 16kHz for server
LOCAL_SAMPLE_RATE = 48000
SERVER_SAMPLE_RATE = 16000
CHUNK_MS = 32
LOCAL_CHUNK_SAMPLES = int(LOCAL_SAMPLE_RATE * CHUNK_MS / 1000)  # 1536 samples
SERVER_CHUNK_SAMPLES = int(SERVER_SAMPLE_RATE * CHUNK_MS / 1000)  # 512 samples


class AudioClient:
    """Streams audio to/from GLaDOS server."""

    def __init__(self, server_host: str, server_port: int):
        self.server_host = server_host
        self.server_port = server_port
        
        self.socket: socket.socket | None = None
        self.running = False
        
        # Playback state
        self.playback_queue = deque()
        self.playback_lock = threading.Lock()
        self.current_playback_rate = LOCAL_SAMPLE_RATE
        self.samples_played = 0  # Debug counter
        self.output_device = None  # Will be set in run()
        
        # Threads
        self.receive_thread: threading.Thread | None = None
        self.playback_thread: threading.Thread | None = None

    def connect(self) -> bool:
        """Connect to the GLaDOS server."""
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.connect((self.server_host, self.server_port))
            self.socket.settimeout(0.1)
            print(f"Connected to GLaDOS at {self.server_host}:{self.server_port}")
            return True
        except Exception as e:
            print(f"Failed to connect: {e}")
            return False

    def _audio_input_callback(self, indata, frames, time, status):
        """Callback for audio input - resamples and sends to server."""
        if status:
            print(f"Input status: {status}", file=sys.stderr)
        
        if self.socket and self.running:
            # Get audio and resample from 48kHz to 16kHz
            audio_48k = indata[:, 0]
            
            # Simple downsampling: take every 3rd sample (48000/16000 = 3)
            # For better quality, use proper resampling
            ratio = SERVER_SAMPLE_RATE / LOCAL_SAMPLE_RATE
            new_len = int(len(audio_48k) * ratio)
            indices = np.linspace(0, len(audio_48k) - 1, new_len)
            audio_16k = np.interp(indices, np.arange(len(audio_48k)), audio_48k).astype(np.float32)
            
            # Convert float32 to int16
            audio_int16 = (audio_16k * 32767).astype(np.int16)
            try:
                self.socket.sendall(audio_int16.tobytes())
            except:
                pass

    def _audio_output_callback(self, outdata, frames, time, status):
        """Callback for audio output - plays received audio."""
        if status:
            print(f"Output status: {status}", file=sys.stderr)
        
        samples_needed = frames
        samples_written = 0
        
        with self.playback_lock:
            while samples_written < samples_needed and self.playback_queue:
                chunk = self.playback_queue[0]
                chunk_samples = len(chunk)
                
                remaining_space = samples_needed - samples_written
                
                if chunk_samples <= remaining_space:
                    # Use entire chunk
                    outdata[samples_written:samples_written + chunk_samples, 0] = chunk
                    samples_written += chunk_samples
                    self.playback_queue.popleft()
                else:
                    # Use partial chunk
                    outdata[samples_written:samples_needed, 0] = chunk[:remaining_space]
                    # Keep remainder for next callback
                    self.playback_queue[0] = chunk[remaining_space:]
                    samples_written = samples_needed
            
            # Track playback progress
            if samples_written > 0:
                self.samples_played += samples_written
                if self.samples_played % 48000 < frames:  # Every ~1 second
                    print(f"Playing audio... {self.samples_played / 48000:.1f}s played, queue: {len(self.playback_queue)}")
            
            # Fill remainder with silence
            if samples_written < samples_needed:
                outdata[samples_written:, 0] = 0

    def _playback_loop(self):
        """Play received audio using sd.play() for reliable playback."""
        while self.running:
            with self.playback_lock:
                if self.playback_queue:
                    audio = self.playback_queue.popleft()
                else:
                    audio = None
            
            if audio is not None:
                print(f"Playing {len(audio)/48000:.2f}s of audio...")
                sd.play(audio, LOCAL_SAMPLE_RATE, device=self.output_device)
                sd.wait()
                print("Playback done")
            else:
                sd.sleep(50)

    def _receive_loop(self):
        """Receive audio from server and queue for playback."""
        buffer = b""
        
        while self.running:
            try:
                data = self.socket.recv(65536)
                if not data:
                    break
                
                buffer += data
                
                # Process complete messages
                while len(buffer) >= 8:
                    # Read header
                    length, sample_rate = struct.unpack("<II", buffer[:8])
                    
                    if length == 0:
                        # Stop playback command
                        with self.playback_lock:
                            self.playback_queue.clear()
                        buffer = buffer[8:]
                        continue
                    
                    # Wait for full audio data
                    if len(buffer) < 8 + length:
                        break
                    
                    audio_bytes = buffer[8:8 + length]
                    buffer = buffer[8 + length:]
                    
                    # Convert to float32
                    audio_int16 = np.frombuffer(audio_bytes, dtype=np.int16)
                    audio_float = audio_int16.astype(np.float32) / 32768.0
                    
                    # Check audio validity
                    max_amp = np.max(np.abs(audio_float))
                    print(f"Received audio: {len(audio_float)} samples @ {sample_rate}Hz, max_amp={max_amp:.3f}")
                    
                    # Resample from server rate to local rate if needed
                    if sample_rate != LOCAL_SAMPLE_RATE:
                        ratio = LOCAL_SAMPLE_RATE / sample_rate
                        new_len = int(len(audio_float) * ratio)
                        indices = np.linspace(0, len(audio_float) - 1, new_len)
                        audio_float = np.interp(indices, np.arange(len(audio_float)), audio_float).astype(np.float32)
                        print(f"Resampled to: {len(audio_float)} samples @ {LOCAL_SAMPLE_RATE}Hz")
                    
                    # Queue for playback directly (don't chunk it - let output callback handle it)
                    with self.playback_lock:
                        self.playback_queue.append(audio_float)
                    print(f"Queued for playback, queue size: {len(self.playback_queue)}")
                    
            except socket.timeout:
                continue
            except Exception as e:
                if self.running:
                    print(f"Receive error: {e}")
                break
        
        print("Receive loop ended")

    def run(self):
        """Main loop - capture and play audio."""
        if not self.connect():
            return
        
        self.running = True
        
        # Start receive thread
        self.receive_thread = threading.Thread(target=self._receive_loop, daemon=True)
        self.receive_thread.start()
        
        print("\n" + "=" * 50)
        print("GLaDOS Audio Client")
        print("=" * 50)
        print("Speak to interact. Press Ctrl+C to exit.")
        print("=" * 50 + "\n")
        
        try:
            # Use pipewire device for proper audio routing
            # Find pipewire device or use default
            devices = sd.query_devices()
            self.output_device = None
            for i, d in enumerate(devices):
                if 'pipewire' in d['name'].lower() and d['max_output_channels'] > 0:
                    self.output_device = i
                    print(f"Using output device: {d['name']}")
                    break
            
            if self.output_device is None:
                print("Using default output device")
            
            # Start playback thread using sd.play() for reliable audio
            self.playback_thread = threading.Thread(target=self._playback_loop, daemon=True)
            self.playback_thread.start()
            
            # Start audio input stream at local (48kHz) sample rate
            with sd.InputStream(
                samplerate=LOCAL_SAMPLE_RATE,
                channels=1,
                dtype=np.float32,
                blocksize=LOCAL_CHUNK_SAMPLES,
                callback=self._audio_input_callback,
            ):
                # Keep running
                while self.running:
                    sd.sleep(100)
                    
        except KeyboardInterrupt:
            print("\nShutting down...")
        finally:
            self.running = False
            if self.socket:
                self.socket.close()


def main():
    parser = argparse.ArgumentParser(description="GLaDOS Network Audio Client")
    parser.add_argument(
        "--server", "-s",
        type=str,
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
    
    client = AudioClient(host, port)
    client.run()


if __name__ == "__main__":
    main()
