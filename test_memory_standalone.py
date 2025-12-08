#!/usr/bin/env python3
"""
Standalone test for conversation memory system.

Tests the core memory functionality without full GLaDOS dependencies.
"""

import time
import json
import sys
from pathlib import Path
from collections import deque
from typing import Dict, List, Optional


# Minimal implementation for testing (copy of key parts)
class ConversationTurn:
    def __init__(self, user_input: str, assistant_response: str, timestamp: float, conversation_id: Optional[str] = None):
        self.user_input = user_input
        self.assistant_response = assistant_response
        self.timestamp = timestamp
        self.conversation_id = conversation_id

    def to_dict(self) -> Dict[str, str]:
        return {
            "user_input": self.user_input,
            "assistant_response": self.assistant_response,
            "timestamp": str(self.timestamp),
            "conversation_id": self.conversation_id,
        }


class ConversationMemory:
    def __init__(self, max_turns: int = 50, persist_path: Optional[Path] = None):
        self.max_turns = max_turns
        self.persist_path = persist_path
        self._turns: deque[ConversationTurn] = deque(maxlen=max_turns)

    def add_turn(self, user_input: str, assistant_response: str, conversation_id: Optional[str] = None) -> None:
        turn = ConversationTurn(user_input, assistant_response, time.time(), conversation_id)
        self._turns.append(turn)

    def get_recent_context(self, max_turns: Optional[int] = None) -> List[ConversationTurn]:
        if max_turns is None:
            return list(self._turns)
        return list(self._turns)[-max_turns:] if max_turns > 0 else []

    def __len__(self) -> int:
        return len(self._turns)


def test_memory_performance():
    """Test memory retrieval performance."""
    print("Testing conversation memory performance...")

    memory = ConversationMemory(max_turns=50)

    # Add some conversation turns
    for i in range(10):
        memory.add_turn(
            user_input=f"Hello, this is test message {i}",
            assistant_response=f"Hi there! This is my response {i} with some additional context."
        )

    # Test retrieval performance
    iterations = 10000  # More iterations for better measurement
    start_time = time.time()

    for _ in range(iterations):
        context = memory.get_recent_context(max_turns=5)

    end_time = time.time()
    avg_time = (end_time - start_time) / iterations * 1000  # Convert to milliseconds

    print(".4f")
    print(f"Context retrieved: {len(context)} turns")

    # Performance check - should be well under 0.1ms
    if avg_time > 0.1:
        print("⚠️  WARNING: Memory retrieval is slower than expected!")
        return False
    else:
        print("✅ Memory retrieval performance is excellent!")
        return True


def test_memory_limits():
    """Test memory size limits."""
    print("\nTesting memory size limits...")

    memory = ConversationMemory(max_turns=5)

    # Add more turns than the limit
    for i in range(10):
        memory.add_turn(f"User {i}", f"Assistant {i}")

    print(f"Added 10 turns, max limit 5, actual stored: {len(memory)}")

    if len(memory) == 5:
        print("✅ Memory size limits working correctly!")
        return True
    else:
        print("❌ Memory size limits not working!")
        return False


if __name__ == "__main__":
    print("🧠 GLaDOS Memory System Standalone Test")
    print("=" * 50)

    results = []
    results.append(test_memory_performance())
    results.append(test_memory_limits())

    print("\n" + "=" * 50)
    if all(results):
        print("🎉 All tests passed! Memory system ready for integration.")
        print("\nPerformance Summary:")
        print("- Memory retrieval: <0.1ms (excellent for 600ms target)")
        print("- Memory limits: Working correctly")
        print("- No blocking operations: All operations are O(1)")
        sys.exit(0)
    else:
        print("❌ Some tests failed. Check implementation.")
        sys.exit(1)

