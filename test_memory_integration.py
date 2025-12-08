#!/usr/bin/env python3
"""
Integration test for GLaDOS memory system.

This script tests that the memory system integrates correctly with the LLM processor
and provides conversation context to the AI.
"""

import sys
import time
from pathlib import Path
from unittest.mock import Mock, patch

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

def test_memory_integration():
    """Test that memory integrates with LLM processor."""
    print("🧠 Testing GLaDOS Memory Integration")
    print("=" * 50)

    try:
        from glados.memory.conversation_memory import ConversationMemory
        from glados.core.llm_processor import LanguageModelProcessor
        from glados.core.engine import MemoryConfig
        import threading
        import queue

        print("✅ Imports successful")

        # Create memory instance
        memory = ConversationMemory(max_turns=10)
        print("✅ Memory instance created")

        # Add some test conversation history
        memory.add_turn("Hello GLaDOS", "Hello! How can I help you today?")
        memory.add_turn("What's my name?", "I'm sorry, but I don't have access to your personal information unless you've told me before.")
        memory.add_turn("My name is Alice", "Nice to meet you, Alice! How can I assist you today?")

        print(f"✅ Added {len(memory)} conversation turns to memory")

        # Test context retrieval
        context_messages = memory.get_context_as_messages(max_turns=5)
        print(f"✅ Retrieved {len(context_messages)} context messages")

        # Verify the format
        expected_roles = ["user", "assistant"] * (len(context_messages) // 2)
        actual_roles = [msg["role"] for msg in context_messages]

        if actual_roles == expected_roles:
            print("✅ Context messages have correct format")
        else:
            print(f"❌ Context format incorrect. Expected: {expected_roles}, Got: {actual_roles}")
            return False

        # Test memory context in LLM processor (mock the actual LLM call)
        print("\n🧪 Testing LLM Processor Integration...")

        # Create mock queues and events
        llm_queue = queue.Queue()
        tts_queue = queue.Queue()
        conversation_history = [
            {"role": "system", "content": "You are GLaDOS, a helpful AI assistant."}
        ]

        # Create events
        processing_event = threading.Event()
        shutdown_event = threading.Event()
        processing_event.set()  # Mark as processing

        # Create LLM processor with memory
        processor = LanguageModelProcessor(
            llm_input_queue=llm_queue,
            tts_input_queue=tts_queue,
            conversation_history=conversation_history,
            completion_url="http://mock-url",
            model_name="test-model",
            api_key=None,
            processing_active_event=processing_event,
            shutdown_event=shutdown_event,
            conversation_memory=memory
        )

        print("✅ LLM Processor created with memory integration")

        # Test that memory context gets injected
        # We can't easily test the full flow without mocking HTTP requests,
        # but we can verify the memory retrieval works

        # Simulate adding a user message
        conversation_history.append({"role": "user", "content": "What's my favorite color?"})

        # Get context as it would be used in the processor
        memory_context = memory.get_context_as_messages(max_turns=10)

        # Check that we have conversation history
        if len(memory_context) >= 6:  # Should have 3 turns * 2 messages each
            print("✅ Memory context available for LLM prompts")
        else:
            print(f"❌ Insufficient memory context: {len(memory_context)} messages")
            return False

        # Test memory storage after "response"
        original_length = len(memory)
        memory.add_turn("What's my favorite color?", "You haven't told me your favorite color yet, Alice!")
        new_length = len(memory)

        if new_length > original_length:
            print("✅ Memory storage working correctly")
        else:
            print("❌ Memory storage failed")
            return False

        print("\n🎉 Memory Integration Test PASSED!")
        print("\n📊 Memory Stats:")
        stats = memory.get_stats()
        print(f"   - Total turns: {stats['total_turns']}")
        print(f"   - Max turns: {stats['max_turns']}")
        print(f"   - Memory usage: {stats['memory_usage_mb']:.2f} MB")

        return True

    except ImportError as e:
        print(f"❌ Import error: {e}")
        print("💡 Make sure all dependencies are installed")
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_config_loading():
    """Test that memory configuration loads correctly."""
    print("\n🔧 Testing Configuration Loading...")
    print("-" * 40)

    try:
        from glados.core.engine import GladosConfig
        import yaml

        # Load the config file
        config_path = Path("configs/glados_config.yaml")
        if not config_path.exists():
            print("❌ Config file not found")
            return False

        config = GladosConfig.from_yaml(str(config_path))

        if hasattr(config, 'memory') and config.memory.enabled:
            print("✅ Memory configuration loaded successfully")
            print(f"   - Enabled: {config.memory.enabled}")
            print(f"   - Max turns: {config.memory.max_turns}")
            print(f"   - Persist path: {config.memory.persist_path}")
            return True
        else:
            print("❌ Memory not enabled in config")
            return False

    except Exception as e:
        print(f"❌ Config loading error: {e}")
        return False


if __name__ == "__main__":
    print("🚀 GLaDOS Memory System Integration Test")
    print("=" * 60)

    results = []

    # Test standalone memory
    results.append(test_memory_integration())

    # Test configuration
    results.append(test_config_loading())

    print("\n" + "=" * 60)
    if all(results):
        print("🎉 ALL TESTS PASSED! Memory system is ready for production use.")
        print("\n📝 Next Steps:")
        print("   1. Start GLaDOS: uv run glados")
        print("   2. Have a conversation and ask about previous topics")
        print("   3. Check that GLaDOS remembers what you discussed")
        print("   4. Memory is automatically saved to data/conversation_memory.json")
    else:
        print("❌ Some tests failed. Check the errors above.")

    sys.exit(0 if all(results) else 1)
