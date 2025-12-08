#!/usr/bin/env python3
"""
GLaDOS Unified Client

A simple GUI client that supports both text and voice input.
Shows conversation history and efficiently handles mic mute detection.

Protocol extensions:
- Text messages: [0xFFFFFFFF][length][utf-8 text]
- Audio: raw int16 samples (as before)
- Server responses include text with audio

Usage:
    python glados_client.py --server localhost:5555
"""

import argparse
import socket
import struct
import sys
import threading
import subprocess
from collections import deque
from dataclasses import dataclass
from enum import Enum
from typing import Optional

import numpy as np

try:
    import sounddevice as sd
except ImportError:
    print("Error: sounddevice not installed. Run: pip install sounddevice")
    sys.exit(1)

try:
    import tkinter as tk
    from tkinter import ttk, scrolledtext
except ImportError:
    print("Error: tkinter not installed")
    sys.exit(1)


# Audio settings
LOCAL_SAMPLE_RATE = 48000
SERVER_SAMPLE_RATE = 16000
CHUNK_MS = 32
LOCAL_CHUNK_SAMPLES = int(LOCAL_SAMPLE_RATE * CHUNK_MS / 1000)

# Protocol constants
TEXT_MESSAGE_MARKER = 0xFFFFFFFF  # Special marker for text messages
ASSISTANT_TEXT_MARKER = 0xFFFFFFFE  # GLaDOS response text
USER_TRANSCRIPTION_MARKER = 0xFFFFFFFD  # User's transcribed speech


class MessageType(Enum):
    USER_TEXT = "user_text"
    USER_VOICE = "user_voice"
    ASSISTANT = "assistant"
    SYSTEM = "system"


@dataclass
class Message:
    type: MessageType
    content: str


class MicMuteDetector:
    """Detects if the microphone is muted at the system level."""
    
    def __init__(self, check_interval_ms: int = 500):
        self.check_interval_ms = check_interval_ms
        self._is_muted = False
        self._last_check = 0
    
    def is_muted(self) -> bool:
        """Check if mic is muted using pactl (PipeWire/PulseAudio)."""
        try:
            # Get default source mute status
            result = subprocess.run(
                ["pactl", "get-source-mute", "@DEFAULT_SOURCE@"],
                capture_output=True,
                text=True,
                timeout=0.5
            )
            self._is_muted = "yes" in result.stdout.lower()
        except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
            # If pactl not available, assume not muted
            self._is_muted = False
        
        return self._is_muted


class GLaDOSClient:
    """Unified GLaDOS client with GUI, text, and voice support."""

    def __init__(self, server_host: str, server_port: int):
        self.server_host = server_host
        self.server_port = server_port
        
        self.socket: Optional[socket.socket] = None
        self.running = False
        
        # Conversation history
        self.messages: list[Message] = []
        
        # Audio playback
        self.playback_queue: deque = deque()
        self.playback_lock = threading.Lock()
        
        # Mic mute detection
        self.mic_detector = MicMuteDetector()
        self.recording_enabled = False
        self.input_stream: Optional[sd.InputStream] = None
        
        # GUI elements (set in create_gui)
        self.root: Optional[tk.Tk] = None
        self.chat_display: Optional[scrolledtext.ScrolledText] = None
        self.text_input: Optional[tk.Entry] = None
        self.mic_status_label: Optional[tk.Label] = None
        self.connection_status: Optional[tk.Label] = None
        
        # Threads
        self.receive_thread: Optional[threading.Thread] = None
        self.playback_thread: Optional[threading.Thread] = None
        self.mic_check_thread: Optional[threading.Thread] = None

    def connect(self) -> bool:
        """Connect to the GLaDOS server."""
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.connect((self.server_host, self.server_port))
            self.socket.settimeout(0.1)
            self.add_message(MessageType.SYSTEM, f"Connected to GLaDOS at {self.server_host}:{self.server_port}")
            return True
        except Exception as e:
            self.add_message(MessageType.SYSTEM, f"Failed to connect: {e}")
            return False

    def add_message(self, msg_type: MessageType, content: str):
        """Add a message to history and update GUI."""
        msg = Message(type=msg_type, content=content)
        self.messages.append(msg)
        
        if self.chat_display and self.root:
            self.root.after(0, self._update_chat_display, msg)

    def _update_chat_display(self, msg: Message):
        """Update the chat display with a new message (must be called from main thread)."""
        self.chat_display.config(state=tk.NORMAL)
        
        # Add appropriate prefix and styling
        if msg.type == MessageType.USER_TEXT:
            prefix = "You (text): "
            tag = "user"
        elif msg.type == MessageType.USER_VOICE:
            prefix = "You (voice): "
            tag = "user"
        elif msg.type == MessageType.ASSISTANT:
            prefix = "GLaDOS: "
            tag = "assistant"
        else:
            prefix = "System: "
            tag = "system"
        
        self.chat_display.insert(tk.END, f"{prefix}{msg.content}\n\n", tag)
        self.chat_display.see(tk.END)
        self.chat_display.config(state=tk.DISABLED)

    def send_text_message(self, text: str):
        """Send a text message to the server."""
        if not self.socket or not text.strip():
            print(f"Cannot send: socket={self.socket}, text='{text}'")
            return
        
        print(f"Sending text message: '{text}'")
        self.add_message(MessageType.USER_TEXT, text)
        
        # Protocol: [0xFFFFFFFF][length][utf-8 text]
        text_bytes = text.encode('utf-8')
        header = struct.pack("<II", TEXT_MESSAGE_MARKER, len(text_bytes))
        
        try:
            self.socket.sendall(header + text_bytes)
            print(f"Text message sent: {len(header) + len(text_bytes)} bytes")
        except Exception as e:
            print(f"Failed to send: {e}")
            self.add_message(MessageType.SYSTEM, f"Failed to send: {e}")

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
        print("Playback loop started", flush=True)
        import time as _time
        loop_count = 0
        while self.running:
            loop_count += 1
            if loop_count % 100 == 0:
                print(f"Playback loop iteration {loop_count}, queue size: {len(self.playback_queue)}", flush=True)
            
            audio = None
            with self.playback_lock:
                if self.playback_queue:
                    audio = self.playback_queue.popleft()
            
            if audio is not None:
                print(f"Playing {len(audio)/LOCAL_SAMPLE_RATE:.2f}s of audio...", flush=True)
                try:
                    sd.play(audio, LOCAL_SAMPLE_RATE, device="pipewire")
                    sd.wait()
                    print("Playback done", flush=True)
                except Exception as e:
                    print(f"Playback error: {e}", flush=True)
            else:
                _time.sleep(0.05)  # Use regular sleep instead of sd.sleep

    def _receive_loop(self):
        """Receive audio and text from server."""
        buffer = b""
        print("Receive loop started")
        
        while self.running:
            try:
                data = self.socket.recv(65536)
                if not data:
                    self.add_message(MessageType.SYSTEM, "Disconnected from server")
                    break
                
                buffer += data
                
                # Process complete messages
                while len(buffer) >= 8:
                    # Read header: [length][sample_rate] or special markers
                    length, second_field = struct.unpack("<II", buffer[:8])
                    
                    # Check for user transcription (speech-to-text result)
                    if length == USER_TRANSCRIPTION_MARKER:
                        text_length = second_field
                        if len(buffer) < 8 + text_length:
                            break
                        text_bytes = buffer[8:8 + text_length]
                        buffer = buffer[8 + text_length:]
                        
                        text = text_bytes.decode('utf-8', errors='replace')
                        print(f"User transcription: {text}")
                        self.add_message(MessageType.USER_VOICE, text)
                        continue
                    
                    # Check for assistant text message from server
                    if length == ASSISTANT_TEXT_MARKER:
                        text_length = second_field
                        if len(buffer) < 8 + text_length:
                            break
                        text_bytes = buffer[8:8 + text_length]
                        buffer = buffer[8 + text_length:]
                        
                        text = text_bytes.decode('utf-8', errors='replace')
                        print(f"Received text: {text}")
                        self.add_message(MessageType.ASSISTANT, text)
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
                    
                    print(f"Received audio: {len(audio_float)} samples @ {sample_rate}Hz")
                    
                    # Resample to local rate
                    if sample_rate != LOCAL_SAMPLE_RATE:
                        ratio = LOCAL_SAMPLE_RATE / sample_rate
                        new_len = int(len(audio_float) * ratio)
                        indices = np.linspace(0, len(audio_float) - 1, new_len)
                        audio_float = np.interp(indices, np.arange(len(audio_float)), audio_float).astype(np.float32)
                        print(f"Resampled to: {len(audio_float)} samples @ {LOCAL_SAMPLE_RATE}Hz")
                    
                    with self.playback_lock:
                        self.playback_queue.append(audio_float)
                        print(f"Queued for playback, queue size: {len(self.playback_queue)}")
                    
            except socket.timeout:
                continue
            except Exception as e:
                self.add_message(MessageType.SYSTEM, f"Receive error: {e}")
                break
        
        self.running = False

    def _mic_check_loop(self):
        """Periodically check mic mute status and start/stop recording."""
        while self.running:
            is_muted = self.mic_detector.is_muted()
            
            if is_muted and self.recording_enabled:
                # Stop recording
                self.recording_enabled = False
                if self.input_stream:
                    self.input_stream.stop()
                if self.root:
                    self.root.after(0, self._update_mic_status, True)
                    
            elif not is_muted and not self.recording_enabled:
                # Start recording
                self.recording_enabled = True
                if self.input_stream:
                    self.input_stream.start()
                if self.root:
                    self.root.after(0, self._update_mic_status, False)
            
            # Check every 200ms
            sd.sleep(200)

    def _update_mic_status(self, is_muted: bool):
        """Update mic status label (must be called from main thread)."""
        if self.mic_status_label:
            if is_muted:
                self.mic_status_label.config(text="🔇 Mic Muted", fg="red")
            else:
                self.mic_status_label.config(text="🎤 Recording", fg="green")

    def _on_send_clicked(self, event=None):
        """Handle send button or Enter key."""
        print("Send clicked!")
        if self.text_input:
            text = self.text_input.get().strip()
            print(f"Text input value: '{text}'")
            if text:
                self.send_text_message(text)
                self.text_input.delete(0, tk.END)

    def _on_close(self):
        """Handle window close."""
        self.running = False
        if self.input_stream:
            self.input_stream.close()
        if self.socket:
            self.socket.close()
        if self.root:
            self.root.destroy()

    def create_gui(self):
        """Create the tkinter GUI."""
        self.root = tk.Tk()
        self.root.title("GLaDOS Client")
        self.root.geometry("600x500")
        self.root.configure(bg="#1a1a1a")
        
        # Configure styles
        style = ttk.Style()
        style.theme_use('clam')
        
        # Main frame
        main_frame = tk.Frame(self.root, bg="#1a1a1a")
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Status bar at top
        status_frame = tk.Frame(main_frame, bg="#1a1a1a")
        status_frame.pack(fill=tk.X, pady=(0, 10))
        
        self.connection_status = tk.Label(
            status_frame, 
            text="● Disconnected", 
            fg="red", 
            bg="#1a1a1a",
            font=("Helvetica", 10)
        )
        self.connection_status.pack(side=tk.LEFT)
        
        self.mic_status_label = tk.Label(
            status_frame,
            text="🔇 Mic Muted",
            fg="red",
            bg="#1a1a1a",
            font=("Helvetica", 10)
        )
        self.mic_status_label.pack(side=tk.RIGHT)
        
        # Chat display
        self.chat_display = scrolledtext.ScrolledText(
            main_frame,
            wrap=tk.WORD,
            state=tk.DISABLED,
            bg="#2a2a2a",
            fg="#ffffff",
            font=("Helvetica", 11),
            insertbackground="white"
        )
        self.chat_display.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        
        # Configure text tags for styling
        self.chat_display.tag_configure("user", foreground="#4a9eff")
        self.chat_display.tag_configure("assistant", foreground="#ffa500")
        self.chat_display.tag_configure("system", foreground="#888888", font=("Helvetica", 9, "italic"))
        
        # Input frame
        input_frame = tk.Frame(main_frame, bg="#1a1a1a")
        input_frame.pack(fill=tk.X)
        
        self.text_input = tk.Entry(
            input_frame,
            bg="#2a2a2a",
            fg="#ffffff",
            insertbackground="white",
            font=("Helvetica", 11)
        )
        self.text_input.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))
        self.text_input.bind("<Return>", self._on_send_clicked)
        self.text_input.focus_set()  # Give focus to text input
        
        send_button = tk.Button(
            input_frame,
            text="Send",
            command=self._on_send_clicked,
            bg="#4a9eff",
            fg="white",
            font=("Helvetica", 10, "bold"),
            padx=20
        )
        send_button.pack(side=tk.RIGHT)
        
        # Handle window close
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        
        # Give initial focus to text input after window is drawn
        self.root.after(100, lambda: self.text_input.focus_force())

    def run(self):
        """Main entry point."""
        # Create GUI first
        self.create_gui()
        
        # Connect to server
        if self.connect():
            self.connection_status.config(text="● Connected", fg="green")
            self.running = True
            
            # Start receive thread
            self.receive_thread = threading.Thread(target=self._receive_loop, daemon=True)
            self.receive_thread.start()
            
            # Start playback thread
            self.playback_thread = threading.Thread(target=self._playback_loop, daemon=True)
            self.playback_thread.start()
            
            # Setup audio input (but don't start until mic is unmuted)
            try:
                self.input_stream = sd.InputStream(
                    samplerate=LOCAL_SAMPLE_RATE,
                    channels=1,
                    dtype=np.float32,
                    blocksize=LOCAL_CHUNK_SAMPLES,
                    callback=self._audio_input_callback
                )
                # Don't start yet - mic check loop will handle it
            except Exception as e:
                self.add_message(MessageType.SYSTEM, f"Audio input error: {e}")
            
            # Start mic check thread
            self.mic_check_thread = threading.Thread(target=self._mic_check_loop, daemon=True)
            self.mic_check_thread.start()
        
        # Run GUI main loop
        self.root.mainloop()


def main():
    parser = argparse.ArgumentParser(description="GLaDOS Unified Client")
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
    
    client = GLaDOSClient(host, port)
    client.run()


if __name__ == "__main__":
    main()
