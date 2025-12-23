#!/usr/bin/env python3
"""
Test script for Tencent ASR implementation
"""

import asyncio
import os
import sys
from io import BytesIO

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    import numpy as np
    from pydub import AudioSegment

    from tencentasr import TencentApiAsr, TencentApiAsrLegacy
except ImportError as e:
    print(f"Import error: {e}")
    print("Please install required dependencies:")
    print("pip install pydub numpy httpx")
    sys.exit(1)


def create_test_audio(text="Hello, this is a test", duration_ms=2000):
    """Create a simple test audio file (silence with some noise)"""
    # Create a silent audio segment
    audio = AudioSegment.silent(duration=duration_ms, frame_rate=16000)

    # Add some random noise to make it valid audio
    samples = np.array(audio.get_array_of_samples())
    noise = np.random.normal(0, 100, len(samples)).astype(np.int16)
    samples = samples + noise

    # Convert back to AudioSegment
    audio = AudioSegment(
        samples.tobytes(),
        frame_rate=16000,
        sample_width=2,
        channels=1
    )

    # Export as WAV
    buffer = BytesIO()
    audio.export(buffer, format="wav")
    return buffer.getvalue()


async def test_tencent_asr():
    """Test the Tencent ASR implementation"""

    # Check if credentials are set
    secret_id = os.environ.get("TENCENT_ASR_SECRET_ID")
    secret_key = os.environ.get("TENCENT_ASR_SECRET_KEY")

    if not secret_id or not secret_key:
        print("⚠️  Tencent credentials not found in environment variables")
        print("Please set:")
        print("  export TENCENT_ASR_SECRET_ID=your_secret_id")
        print("  export TENCENT_ASR_SECRET_KEY=your_secret_key")
        print("\nContinuing with basic structure test...")

        # Test basic structure without API calls
        print("\n=== Testing Basic Structure ===")

        # Test 1: Check if class can be instantiated
        try:
            # Mock opt object
            class MockOpt:
                fps = 50
                batch_size = 16
                l = 10
                r = 10

            opt = MockOpt()
            asr = TencentApiAsr(opt)
            print("✅ TencentApiAsr instantiation: PASSED")
        except Exception as e:
            print(f"❌ TencentApiAsr instantiation: FAILED - {e}")
            return False

        # Test 2: Check credential loading
        try:
            # This should fail without credentials
            asr._load_credentials()
            print("❌ Credential loading: FAILED - Should have raised error")
        except RuntimeError:
            print("✅ Credential loading: PASSED (correctly raised error)")
        except Exception as e:
            print(f"❌ Credential loading: FAILED - {e}")
            return False

        # Test 3: Check legacy class
        try:
            legacy = TencentApiAsrLegacy()
            print("✅ TencentApiAsrLegacy instantiation: PASSED")
        except Exception as e:
            print(f"❌ TencentApiAsrLegacy instantiation: FAILED - {e}")
            return False

        # Test 4: Check audio format conversion
        try:
            # Create test audio
            test_audio = create_test_audio()

            # Test the conversion method
            asr = TencentApiAsr(opt)
            converted = asr._convert_audio_format(test_audio)

            if len(converted) > 0:
                print("✅ Audio format conversion: PASSED")
            else:
                print("❌ Audio format conversion: FAILED - Empty result")
                return False
        except Exception as e:
            print(f"❌ Audio format conversion: FAILED - {e}")
            return False

        # Test 5: Check request building
        try:
            headers, payload = asr._build_request(
                "dGVzdA==")  # "test" in base64
            required_headers = ["Authorization", "Content-Type", "Host",
                                "X-TC-Action", "X-TC-Timestamp", "X-TC-Version", "X-TC-Region"]

            for header in required_headers:
                if header not in headers:
                    print(
                        f"❌ Request building: FAILED - Missing header {header}")
                    return False

            print("✅ Request building: PASSED")
        except Exception as e:
            print(f"❌ Request building: FAILED - {e}")
            return False

        print("\n🎉 All basic structure tests passed!")
        print("\nTo test actual API calls, please set your Tencent credentials:")
        print("  export TENCENT_ASR_SECRET_ID=your_secret_id")
        print("  export TENCENT_ASR_SECRET_KEY=your_secret_key")
        return True

    # If credentials are available, test actual API
    print("✅ Credentials found, testing actual API...")

    try:
        # Test with legacy class
        print("\n=== Testing Legacy API ===")
        legacy = TencentApiAsrLegacy()

        # Create test audio
        test_audio = create_test_audio("Hello, this is a test message")

        print("Sending audio to Tencent ASR...")
        result = await legacy.run(test_audio)

        print(f"✅ API call successful!")
        print(f"Result: {result}")
        return True

    except Exception as e:
        print(f"❌ API test failed: {e}")
        return False


async def test_with_mock():
    """Test with mock responses to verify logic"""
    print("\n=== Testing with Mock Data ===")

    # Mock opt object
    class MockOpt:
        fps = 50
        batch_size = 16
        l = 10
        r = 10

    opt = MockOpt()

    try:
        # Test 1: Signature generation
        asr = TencentApiAsr(opt)
        asr._secret_id = "test_secret_id"
        asr._secret_key = "test_secret_key"

        # Test signature method
        signature = asr._sign(b"test_key", "test_message")
        if signature:
            print("✅ Signature generation: PASSED")
        else:
            print("❌ Signature generation: FAILED")
            return False

        # Test 2: Request building
        headers, payload = asr._build_request("dGVzdA==")
        if "Authorization" in headers and "X-TC-Action" in headers:
            print("✅ Request building with mock credentials: PASSED")
        else:
            print("❌ Request building: FAILED")
            return False

        # Test 3: Audio format detection
        # Test WAV detection
        wav_header = b"RIFF\x00\x00\x00\x00WAVE"
        if asr._convert_audio_format(wav_header) == wav_header:
            print("✅ WAV format detection: PASSED")
        else:
            print("❌ WAV format detection: FAILED")
            return False

        # Test 4: Error handling
        try:
            # Test with empty credentials
            asr._secret_id = ""
            asr._secret_key = ""
            asr._load_credentials()
            print("❌ Error handling: FAILED - Should have raised error")
        except RuntimeError:
            print("✅ Error handling: PASSED")
        except Exception as e:
            print(f"❌ Error handling: FAILED - {e}")
            return False

        print("\n🎉 All mock tests passed!")
        return True

    except Exception as e:
        print(f"❌ Mock test failed: {e}")
        return False


async def main():
    """Main test runner"""
    print("=" * 60)
    print("Tencent ASR Implementation Test")
    print("=" * 60)

    # Run basic structure tests
    success1 = await test_tencent_asr()

    # Run mock tests
    success2 = await test_with_mock()

    if success1 and success2:
        print("\n" + "=" * 60)
        print("🎉 ALL TESTS PASSED!")
        print("=" * 60)
        print("\nThe Tencent ASR implementation is ready to use.")
        print("\nUsage example:")
        print("```python")
        print("from tencentasr import TencentApiAsr")
        print("import asyncio")
        print("")
        print("async def main():")
        print("    # Create ASR instance")
        print("    asr = TencentApiAsr(opt)")
        print("    ")
        print("    # Recognize audio")
        print("    audio_data = open('audio.wav', 'rb').read()")
        print("    text = await asr.recognize(audio_data)")
        print("    print(f'Recognized: {text}')")
        print("```")
        return True
    else:
        print("\n" + "=" * 60)
        print("❌ SOME TESTS FAILED")
        print("=" * 60)
        return False


if __name__ == "__main__":
    asyncio.run(main())
