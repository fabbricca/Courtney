#!/usr/bin/env python3
"""
GLaDOS Textual TUI Client

Beautiful terminal interface for GLaDOS using Textual framework.
Reuses core networking logic from glados_network_client.

Usage:
    python glados_textual_client.py --server localhost:5555
"""

import argparse
import sys
import threading
from datetime import datetime
from pathlib import Path
from typing import List, Optional

try:
    from textual.app import App, ComposeResult
    from textual.containers import Container, Vertical, Horizontal
    from textual.widgets import Header, Footer, Static, Input, RichLog
    from textual.binding import Binding
    from rich.text import Text
except ImportError:
    print("Error: textual not installed. Run: pip install textual")
    sys.exit(1)

from glados_network_client import GLaDOSNetworkClient


class StatusBar(Static):
    """Status bar showing connection and mic status."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.connected = False
        self.mic_muted = True
        self.server_address = ""

    def update_connection(self, connected: bool, address: str = ""):
        """Update connection status."""
        self.connected = connected
        self.server_address = address
        self.refresh_display()

    def update_mic(self, is_muted: bool):
        """Update mic status."""
        self.mic_muted = is_muted
        self.refresh_display()

    def refresh_display(self):
        """Refresh the status display."""
        # Connection status
        if self.connected:
            conn_icon = "🟢"
            conn_text = f"Connected to {self.server_address}"
        else:
            conn_icon = "🔴"
            conn_text = "Disconnected"

        # Mic status
        if self.mic_muted:
            mic_icon = "🔇"
            mic_text = "Muted"
        else:
            mic_icon = "🎤"
            mic_text = "Recording"

        # Build status text
        status = Text()
        status.append(f"{conn_icon} {conn_text}    ", style="bold cyan")
        status.append(f"{mic_icon} {mic_text}", style="bold yellow" if self.mic_muted else "bold green")

        self.update(status)


class MessageDisplay(RichLog):
    """Scrollable message display area."""

    def __init__(self, **kwargs):
        super().__init__(
            highlight=True,
            markup=True,
            wrap=True,
            auto_scroll=True,
            **kwargs
        )

    def add_user_message(self, text: str, via_voice: bool = False):
        """Add a user message."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        prefix = "You (voice)" if via_voice else "You"

        msg = Text()
        msg.append(f"[{timestamp}] ", style="dim")
        msg.append(f"{prefix}: ", style="bold blue")
        msg.append(text, style="white")

        self.write(msg)

    def add_assistant_message(self, text: str):
        """Add an assistant message."""
        timestamp = datetime.now().strftime("%H:%M:%S")

        msg = Text()
        msg.append(f"[{timestamp}] ", style="dim")
        msg.append("GLaDOS: ", style="bold yellow")
        msg.append(text, style="white")

        self.write(msg)

    def add_system_message(self, text: str):
        """Add a system message."""
        timestamp = datetime.now().strftime("%H:%M:%S")

        msg = Text()
        msg.append(f"[{timestamp}] ", style="dim")
        msg.append("System: ", style="bold red")
        msg.append(text, style="dim")

        self.write(msg)


class MessageInput(Input):
    """Enhanced input widget with message history."""

    def __init__(self, **kwargs):
        super().__init__(
            placeholder="Type your message... (Ctrl+W: delete word, Up/Down: history, Enter: send)",
            **kwargs
        )
        self.history: List[str] = []
        self.history_index = -1
        self.current_draft = ""

    def on_key(self, event) -> None:
        """Handle special key combinations."""
        # Ctrl+W: Delete word
        if event.key == "ctrl+w":
            self.delete_word()
            event.prevent_default()
            event.stop()

        # Ctrl+U: Clear line
        elif event.key == "ctrl+u":
            self.value = ""
            event.prevent_default()
            event.stop()

        # Up arrow: Previous message from history
        elif event.key == "up":
            if self.history:
                if self.history_index == -1:
                    # Save current draft
                    self.current_draft = self.value
                    self.history_index = len(self.history) - 1
                elif self.history_index > 0:
                    self.history_index -= 1

                if 0 <= self.history_index < len(self.history):
                    self.value = self.history[self.history_index]
            event.prevent_default()
            event.stop()

        # Down arrow: Next message from history
        elif event.key == "down":
            if self.history and self.history_index >= 0:
                self.history_index += 1

                if self.history_index >= len(self.history):
                    # Restore draft
                    self.value = self.current_draft
                    self.history_index = -1
                else:
                    self.value = self.history[self.history_index]
            event.prevent_default()
            event.stop()

    def delete_word(self):
        """Delete the last word (like bash Ctrl+W)."""
        value = self.value
        # Strip trailing whitespace
        value = value.rstrip()
        # Find last space
        last_space = value.rfind(' ')
        if last_space >= 0:
            self.value = value[:last_space + 1]
        else:
            self.value = ""

    def add_to_history(self, message: str):
        """Add message to history."""
        if message and (not self.history or message != self.history[-1]):
            self.history.append(message)
            # Keep last 100 messages
            if len(self.history) > 100:
                self.history.pop(0)
        self.history_index = -1
        self.current_draft = ""


class GLaDOSTUI(App):
    """GLaDOS Textual TUI Application."""

    CSS = """
    Screen {
        background: $surface;
    }

    #main-container {
        height: 100%;
    }

    #messages {
        height: 1fr;
        border: solid $primary;
        padding: 1;
        background: $surface-darken-1;
    }

    #status {
        height: 1;
        background: $boost;
        padding: 0 1;
        color: $text;
    }

    #input-container {
        height: auto;
        padding: 0 1 1 1;
    }

    MessageInput {
        border: solid $accent;
    }
    """

    BINDINGS = [
        Binding("ctrl+c", "quit", "Quit", show=True),
        Binding("ctrl+l", "clear_messages", "Clear", show=True),
        ("ctrl+q", "quit", "Quit"),
    ]

    def __init__(
        self,
        server_host: str,
        server_port: int,
        auth_token: Optional[str] = None,
        auth_token_file: Optional[Path] = None,
    ):
        super().__init__()
        self.server_host = server_host
        self.server_port = server_port
        self.auth_token = auth_token
        self.auth_token_file = auth_token_file
        self.client: GLaDOSNetworkClient = None
        self.title = "GLaDOS v2.1 - Modern TUI"
        self._shutting_down = False

    def compose(self) -> ComposeResult:
        """Create child widgets."""
        yield Header(show_clock=True)

        with Vertical(id="main-container"):
            yield StatusBar(id="status")
            yield MessageDisplay(id="messages")

            with Container(id="input-container"):
                yield MessageInput(id="input")

        yield Footer()

    def on_mount(self) -> None:
        """Initialize when app starts."""
        # Get widgets
        self.messages = self.query_one("#messages", MessageDisplay)
        self.status_bar = self.query_one("#status", StatusBar)
        self.input_widget = self.query_one("#input", MessageInput)

        # Focus input
        self.input_widget.focus()

        # Initialize network client
        self.client = GLaDOSNetworkClient(
            server_host=self.server_host,
            server_port=self.server_port,
            on_user_text=self.on_user_text,
            on_user_voice=self.on_user_voice,
            on_assistant_text=self.on_assistant_text,
            on_connection_status=self.on_connection_status,
            on_mic_status=self.on_mic_status,
            auth_token=self.auth_token,
            auth_token_file=self.auth_token_file,
        )

        # Connect to server
        self.messages.add_system_message(f"Connecting to {self.server_host}:{self.server_port}...")

        if self.client.connect():
            self.messages.add_system_message("Connected successfully!")
            self.status_bar.update_connection(True, f"{self.server_host}:{self.server_port}")

            # Start client
            if self.client.start():
                self.messages.add_system_message("All systems operational. Start chatting!")
            else:
                self.messages.add_system_message("Failed to start client threads")
        else:
            self.messages.add_system_message("Failed to connect to server!")
            self.messages.add_system_message("Check that the server is running: ./scripts/start_server.sh")
            self.status_bar.update_connection(False)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle input submission."""
        text = event.value.strip()

        if not text:
            return

        # Check for quit command
        if text.lower() in ('quit', 'exit', 'q'):
            self.action_quit()
            return

        # Add to history
        self.input_widget.add_to_history(text)

        # Send message
        if self.client and self.client.is_connected():
            # Note: We don't display the message here anymore
            # The server will echo it back, which prevents duplication
            self.client.send_text_message(text)
        else:
            self.messages.add_system_message("Not connected to server!")

        # Clear input
        self.input_widget.value = ""

    def _safe_call(self, callback, *args, **kwargs):
        """
        Call a function safely from any thread.

        If we're in the app thread, call directly.
        Otherwise, use call_from_thread.
        """
        if self._shutting_down:
            return

        # Check if we're in the app thread
        if hasattr(self, '_thread_id') and self._thread_id == threading.get_ident():
            # We're in the app thread, call directly
            callback(*args, **kwargs)
        else:
            # We're in a different thread, use call_from_thread
            self.call_from_thread(callback, *args, **kwargs)

    def on_user_text(self, text: str) -> None:
        """Callback: User sent text message."""
        # Display in messages (this is the echo from server, not client-side)
        self._safe_call(self.messages.add_user_message, text, via_voice=False)

    def on_user_voice(self, text: str) -> None:
        """Callback: User spoke (transcription from server)."""
        self._safe_call(self.messages.add_user_message, text, via_voice=True)

    def on_assistant_text(self, text: str) -> None:
        """Callback: Assistant sent message."""
        self._safe_call(self.messages.add_assistant_message, text)

    def on_connection_status(self, connected: bool) -> None:
        """Callback: Connection status changed."""
        address = f"{self.server_host}:{self.server_port}" if connected else ""
        self._safe_call(self.status_bar.update_connection, connected, address)

        if not connected:
            self._safe_call(self.messages.add_system_message, "Disconnected from server")

    def on_mic_status(self, is_muted: bool) -> None:
        """Callback: Mic status changed."""
        self._safe_call(self.status_bar.update_mic, is_muted)

    def action_clear_messages(self) -> None:
        """Clear message display."""
        self.messages.clear()
        self.messages.add_system_message("Messages cleared")

    def action_quit(self) -> None:
        """Quit the application."""
        self._shutting_down = True
        if self.client:
            self.client.stop()
        self.exit()

    def on_unmount(self) -> None:
        """Cleanup when app closes."""
        self._shutting_down = True
        if self.client:
            self.client.stop()


def main():
    """Entry point."""
    parser = argparse.ArgumentParser(description="GLaDOS Textual TUI Client")
    parser.add_argument(
        "--server",
        default="localhost:5555",
        help="Server address (host:port)"
    )
    parser.add_argument(
        "--auth-token",
        type=str,
        default=None,
        help="JWT authentication token (optional, v2.1+)",
    )
    parser.add_argument(
        "--auth-token-file",
        type=str,
        default=None,
        help="Path to file containing JWT token (optional, v2.1+)",
    )
    args = parser.parse_args()

    # Parse server address
    if ":" in args.server:
        host, port = args.server.rsplit(":", 1)
        port = int(port)
    else:
        host = args.server
        port = 5555

    # Convert auth_token_file to Path if provided
    auth_token_file = Path(args.auth_token_file) if args.auth_token_file else None

    # Run TUI
    app = GLaDOSTUI(
        server_host=host,
        server_port=port,
        auth_token=args.auth_token,
        auth_token_file=auth_token_file,
    )
    app.run()


if __name__ == "__main__":
    main()
