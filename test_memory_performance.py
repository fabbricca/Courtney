#!/usr/bin/env python3
"""
Performance test for conversation memory system.

This script tests that the memory system doesn't impact latency
and works correctly with the conversation flow.
"""

import time
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent / "src"))

from glados.memory.conversation_memory import ConversationMemory


def test_memory_performance():
    """Test memory retrieval performance."""
    print("Testing conversation memory performance...")

    # Create memory instance
    memory = ConversationMemory(max_turns=50, persist_path=None)

    # Add some conversation turns
    for i in range(10):
        memory.add_turn(
            user_input=f"Hello, this is test message {i}",
            assistant_response=f"Hi there! This is my response {i} with some additional context to make it more realistic."
        )

    # Test retrieval performance
    iterations = 1000
    start_time = time.time()

    for _ in range(iterations):
        context = memory.get_recent_context(max_turns=5)

    end_time = time.time()
    avg_time = (end_time - start_time) / iterations * 1000  # Convert to milliseconds

    print(".2f")
    print(f"Context retrieved: {len(context)} turns")
    print(f"Memory usage: {memory.get_stats()['memory_usage_mb']:.2f} MB")

    # Performance check - should be well under 1ms
    if avg_time > 1.0:
        print("⚠️  WARNING: Memory retrieval is slower than expected!")
        return False
    else:
        print("✅ Memory retrieval performance is excellent!")
        return True


def test_memory_limits():
    """Test memory size limits."""
    print("\nTesting memory size limits...")

    memory = ConversationMemory(max_turns=5, persist_path=None)

    # Add more turns than the limit
    for i in range(10):
        memory.add_turn(f"User {i}", f"Assistant {i}")

    stats = memory.get_stats()
    print(f"Added 10 turns, max limit 5, actual stored: {stats['total_turns']}")

    if stats['total_turns'] == 5:
        print("✅ Memory size limits working correctly!")
        return True
    else:
        print("❌ Memory size limits not working!")
        return False


def test_memory_persistence():
    """Test memory persistence (basic)."""
    print("\nTesting memory persistence...")

    import tempfile
    import os

    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        temp_path = f.name

    try:
        # Create memory with persistence
        memory1 = ConversationMemory(max_turns=10, persist_path=Path(temp_path))
        memory1.add_turn("Test user", "Test assistant")
        memory1._persist_to_disk()  # Force persistence

        # Create new instance and load
        memory2 = ConversationMemory(max_turns=10, persist_path=Path(temp_path))

        if len(memory2) == 1:
            print("✅ Memory persistence working!")
            return True
        else:
            print("❌ Memory persistence not working!")
            return False

    finally:
        if os.path.exists(temp_path):
            os.unlink(temp_path)


if __name__ == "__main__":
    print("🧠 GLaDOS Memory System Performance Test")
    print("=" * 50)

    results = []
    results.append(test_memory_performance())
    results.append(test_memory_limits())
    results.append(test_memory_persistence())

    print("\n" + "=" * 50)
    if all(results):
        print("🎉 All tests passed! Memory system ready for integration.")
        sys.exit(0)
    else:
        print("❌ Some tests failed. Check implementation.")
        sys.exit(1)

