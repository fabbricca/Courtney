#!/usr/bin/env python3
"""Test script for RVC voice cloning integration.

Supports two modes:
1. Service mode (Docker): RVC runs in a container, GLaDOS calls it via HTTP
2. Inline mode: RVC runs directly in the same process

Usage:
    # Test service mode (Docker must be running)
    python test_rvc.py service
    
    # Test inline mode (requires rvc-python installed)
    python test_rvc.py inline
"""

import sys
import time

# Configuration
RVC_SERVICE_URL = "http://localhost:5050"
RVC_MODEL_NAME = None  # Set to your model folder name in rvc_models/

# For inline mode
RVC_MODEL_PATH = "/path/to/your/model.pth"
RVC_INDEX_PATH = None

BASE_VOICE = "glados"

TEST_TEXTS = [
    "Hello, this is a test of voice cloning.",
    "The quick brown fox jumps over the lazy dog.",
    "Testing, testing, one two three.",
]


def test_rvc_service():
    """Test RVC Docker service."""
    print("\n=== Testing RVC Docker Service ===")
    
    try:
        from glados.TTS.rvc_service import RVCServiceClient
    except ImportError as e:
        print(f"❌ Failed to import RVC service client: {e}")
        return False
    
    import numpy as np
    
    client = RVCServiceClient(
        service_url=RVC_SERVICE_URL,
        model_name=RVC_MODEL_NAME,
    )
    
    if not client.initialize():
        print("❌ Failed to connect to RVC service")
        print("   Make sure the RVC Docker container is running:")
        print("   cd rvc && docker compose up -d")
        return False
    
    print("✓ Connected to RVC service")
    
    # Test with a sine wave
    sample_rate = 22050
    duration = 2.0
    t = np.linspace(0, duration, int(sample_rate * duration), dtype=np.float32)
    audio = 0.3 * np.sin(2 * np.pi * 440 * t)
    
    print(f"Input: {len(audio)} samples ({duration}s) at {sample_rate}Hz")
    
    start = time.time()
    converted = client.convert(audio, sample_rate)
    elapsed = time.time() - start
    
    print(f"✓ Conversion took {elapsed*1000:.1f}ms")
    print(f"  Output: {len(converted)} samples")
    
    return True


def test_rvc_service_with_tts():
    """Test RVC service with TTS integration."""
    print("\n=== Testing RVC Service + TTS ===")
    
    try:
        from glados.TTS import get_speech_synthesizer
        from glados.TTS.rvc_service import RVCServiceClient, RVCServiceSynthesizer
    except ImportError as e:
        print(f"❌ Failed to import: {e}")
        return False
    
    # Create base TTS
    base_tts = get_speech_synthesizer(BASE_VOICE)
    
    # Create RVC client
    rvc_client = RVCServiceClient(
        service_url=RVC_SERVICE_URL,
        model_name=RVC_MODEL_NAME,
    )
    
    if not rvc_client.initialize():
        print("❌ RVC service not available")
        return False
    
    # Wrap TTS with RVC
    tts = RVCServiceSynthesizer(base_tts, rvc_client)
    
    print(f"✓ TTS+RVC service initialized, sample rate: {tts.sample_rate}Hz")
    
    for text in TEST_TEXTS:
        print(f"\nSynthesizing: '{text}'")
        
        start = time.time()
        audio = tts.generate_speech_audio(text)
        elapsed = time.time() - start
        
        duration = len(audio) / tts.sample_rate
        print(f"  ✓ Generated {duration:.2f}s audio in {elapsed*1000:.0f}ms")
        if duration > 0:
            print(f"    Real-time factor: {elapsed/duration:.2f}x")
    
    return True


def test_rvc_inline():
    """Test RVC converter directly without TTS (inline mode)."""
    print("\n=== Testing RVC Inline Mode ===")
    
    try:
        from glados.TTS.rvc_wrapper import RVCVoiceConverter
    except ImportError as e:
        print(f"❌ Failed to import RVC wrapper: {e}")
        print("   Install with: pip install rvc-python")
        return False
    
    import numpy as np
    
    try:
        converter = RVCVoiceConverter(
            model_path=RVC_MODEL_PATH,
            index_path=RVC_INDEX_PATH,
            device="cuda:0",
            f0_method="rmvpe",
        )
    except Exception as e:
        print(f"❌ Failed to load RVC model: {e}")
        return False
    
    # Create a test sine wave
    sample_rate = 22050
    duration = 2.0
    t = np.linspace(0, duration, int(sample_rate * duration), dtype=np.float32)
    audio = 0.3 * np.sin(2 * np.pi * 440 * t)
    
    print(f"Input audio: {len(audio)} samples ({duration}s) at {sample_rate}Hz")
    
    start = time.time()
    converted = converter.convert(audio, sample_rate)
    elapsed = time.time() - start
    
    print(f"✓ Conversion took {elapsed*1000:.1f}ms")
    print(f"  Output: {len(converted)} samples")
    
    return True


def test_rvc_inline_with_tts():
    """Test RVC with TTS integration (inline mode)."""
    print("\n=== Testing RVC Inline + TTS ===")
    
    try:
        from glados.TTS import get_speech_synthesizer
    except ImportError as e:
        print(f"❌ Failed to import TTS: {e}")
        return False
    
    try:
        # Create TTS with RVC
        tts = get_speech_synthesizer(
            voice=BASE_VOICE,
            rvc_model_path=RVC_MODEL_PATH,
            rvc_index_path=RVC_INDEX_PATH,
            rvc_device="cuda:0",
            rvc_f0_method="rmvpe",
        )
    except ImportError as e:
        print(f"❌ RVC not available: {e}")
        return False
    except Exception as e:
        print(f"❌ Failed to initialize TTS+RVC: {e}")
        return False
    
    print(f"✓ TTS+RVC initialized, sample rate: {tts.sample_rate}Hz")
    
    for text in TEST_TEXTS:
        print(f"\nSynthesizing: '{text}'")
        
        start = time.time()
        audio = tts.generate_speech_audio(text)
        elapsed = time.time() - start
        
        duration = len(audio) / tts.sample_rate
        print(f"  ✓ Generated {duration:.2f}s audio in {elapsed*1000:.0f}ms")
        if duration > 0:
            print(f"    Real-time factor: {elapsed/duration:.2f}x")
    
    return True


def test_service_latency():
    """Measure RVC service latency for different audio lengths."""
    print("\n=== Service Latency Benchmarks ===")
    
    try:
        from glados.TTS.rvc_service import RVCServiceClient
    except ImportError:
        print("❌ RVC service client not available")
        return False
    
    import numpy as np
    
    client = RVCServiceClient(
        service_url=RVC_SERVICE_URL,
        model_name=RVC_MODEL_NAME,
    )
    
    if not client.initialize():
        print("❌ RVC service not available")
        return False
    
    sample_rate = 22050
    
    # Test different audio lengths
    for duration in [0.5, 1.0, 2.0, 5.0]:
        t = np.linspace(0, duration, int(sample_rate * duration), dtype=np.float32)
        audio = 0.3 * np.sin(2 * np.pi * 440 * t)
        
        # Warm up
        _ = client.convert(audio, sample_rate)
        
        # Measure
        times = []
        for _ in range(3):
            start = time.time()
            _ = client.convert(audio, sample_rate)
            times.append(time.time() - start)
        
        avg = sum(times) / len(times)
        print(f"  {duration:.1f}s audio: {avg*1000:.0f}ms avg ({avg/duration:.2f}x realtime)")
    
    return True


if __name__ == "__main__":
    import os
    
    mode = sys.argv[1] if len(sys.argv) > 1 else "service"
    
    print("RVC Voice Cloning Test")
    print("=" * 50)
    print(f"Mode: {mode}")
    
    if mode == "service":
        print(f"Service URL: {RVC_SERVICE_URL}")
        print(f"Model name: {RVC_MODEL_NAME or 'default'}")
        print()
        
        test_rvc_service()
        test_rvc_service_with_tts()
        test_service_latency()
        
    elif mode == "inline":
        if not os.path.exists(RVC_MODEL_PATH):
            print(f"⚠️  RVC model not found at: {RVC_MODEL_PATH}")
            print("   Please set RVC_MODEL_PATH in this script")
            sys.exit(1)
        
        print(f"Model: {RVC_MODEL_PATH}")
        print(f"Index: {RVC_INDEX_PATH or 'None'}")
        print()
        
        test_rvc_inline()
        test_rvc_inline_with_tts()
        
    else:
        print(f"Unknown mode: {mode}")
        print("Usage: python test_rvc.py [service|inline]")
        sys.exit(1)
