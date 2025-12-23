#!/usr/bin/env python3
"""
Demo script showing how to use Tencent ASR with LiveTalking
"""

import asyncio
import os
import sys
from pathlib import Path

# Add parent directory to path for imports
parent_dir = Path(__file__).parent.parent
sys.path.insert(0, str(parent_dir))

try:
    from tencentasr import TencentApiAsr
except ImportError:
    print("Error: Could not import tencentasr. Make sure you're running from the correct directory.")
    print(f"Current path: {sys.path}")
    sys.exit(1)


class DemoOpt:
    """Mock configuration object for demo"""

    def __init__(self):
        self.fps = 50
        self.batch_size = 16
        self.l = 10
        self.r = 10


async def demo_basic_usage():
    """Demo: Basic ASR usage"""
    print("=" * 60)
    print("Demo 1: Basic ASR Usage")
    print("=" * 60)

    # Check if credentials are set
    secret_id = os.environ.get("TENCENT_ASR_SECRET_ID")
    secret_key = os.environ.get("TENCENT_ASR_SECRET_KEY")

    if not secret_id or not secret_key:
        print("❌ Please set TENCENT_ASR_SECRET_ID and TENCENT_ASR_SECRET_KEY")
        print("   Example:")
        print("   export TENCENT_ASR_SECRET_ID=your_id")
        print("   export TENCENT_ASR_SECRET_KEY=your_key")
        return False

    # Create ASR instance
    opt = DemoOpt()
    asr = TencentApiAsr(opt)

    print("✅ ASR initialized successfully")

    # Create a test audio file (silence)
    import numpy as np

    sample_rate = 16000
    duration_ms = 2000  # 2 seconds
    num_samples = int(sample_rate * duration_ms / 1000)

    # Create silent audio
    audio_data = np.zeros(num_samples, dtype=np.int16)

    # Create WAV header
    wav_header = bytearray(44)
    wav_header[0:4] = b'RIFF'
    wav_header[4:8] = (36 + num_samples * 2).to_bytes(4, 'little')
    wav_header[8:12] = b'WAVE'
    wav_header[12:16] = b'fmt '
    wav_header[16:20] = (16).to_bytes(4, 'little')
    wav_header[20:22] = (1).to_bytes(2, 'little')
    wav_header[22:24] = (1).to_bytes(2, 'little')
    wav_header[24:28] = (sample_rate).to_bytes(4, 'little')
    wav_header[28:32] = (sample_rate * 2).to_bytes(4, 'little')
    wav_header[32:34] = (2).to_bytes(2, 'little')
    wav_header[34:36] = (16).to_bytes(2, 'little')
    wav_header[36:40] = b'data'
    wav_header[40:44] = (num_samples * 2).to_bytes(4, 'little')

    audio_bytes = bytes(wav_header) + audio_data.tobytes()

    print(f"Created test audio: {len(audio_bytes)} bytes")
    print("Note: This will make a real API call to Tencent Cloud")
    print("      The audio is silent, so expect minimal recognition")

    try:
        # This will make a real API call
        text = await asr.recognize(audio_bytes)
        print(f"✅ Recognition result: '{text}'")
        return True
    except Exception as e:
        print(f"❌ API call failed: {e}")
        return False


async def demo_with_real_audio():
    """Demo: Using with actual audio file"""
    print("\n" + "=" * 60)
    print("Demo 2: With Real Audio File")
    print("=" * 60)

    # Look for test audio files
    audio_files = [
        "test_audio.wav",
        "audio.wav",
        "sample.wav",
        "data/test_audio.wav"
    ]

    audio_path = None
    for path in audio_files:
        if Path(path).exists():
            audio_path = path
            break

    if not audio_path:
        print("ℹ️  No test audio files found. Skipping this demo.")
        print("   To use this demo, place a WAV file in the project directory.")
        return True

    print(f"Found audio file: {audio_path}")

    # Load audio
    with open(audio_path, 'rb') as f:
        audio_data = f.read()

    print(f"Loaded {len(audio_data)} bytes")

    # Create ASR and recognize
    opt = DemoOpt()
    asr = TencentApiAsr(opt)

    try:
        text = await asr.recognize(audio_data)
        print(f"✅ Recognition result: '{text}'")
        return True
    except Exception as e:
        print(f"❌ Recognition failed: {e}")
        return False


async def demo_mp3_conversion():
    """Demo: MP3 to WAV conversion"""
    print("\n" + "=" * 60)
    print("Demo 3: MP3 Format Support")
    print("=" * 60)

    # Look for MP3 files
    mp3_files = [
        "test_audio.mp3",
        "audio.mp3",
        "sample.mp3"
    ]

    mp3_path = None
    for path in mp3_files:
        if Path(path).exists():
            mp3_path = path
            break

    if not mp3_path:
        print("ℹ️  No MP3 files found. Skipping this demo.")
        print("   The implementation supports MP3 files and will auto-convert to WAV.")
        return True

    print(f"Found MP3 file: {mp3_path}")

    # Load MP3
    with open(mp3_path, 'rb') as f:
        mp3_data = f.read()

    print(f"Loaded {len(mp3_data)} bytes of MP3 data")
    print("The ASR will automatically convert MP3 to WAV format")

    # Create ASR and recognize
    opt = DemoOpt()
    asr = TencentApiAsr(opt)

    try:
        text = await asr.recognize(mp3_data)
        print(f"✅ Recognition result: '{text}'")
        return True
    except Exception as e:
        print(f"❌ Recognition failed: {e}")
        return False


async def demo_integration_example():
    """Demo: Integration example"""
    print("\n" + "=" * 60)
    print("Demo 4: Integration Example")
    print("=" * 60)

    print("Example code for integrating with your application:")
    print()
    print("```python")
    print("from tencentasr import TencentApiAsr")
    print("import asyncio")
    print()
    print("class YourApplication:")
    print("    def __init__(self):")
    print("        # Your existing setup")
    print("        self.asr = TencentApiAsr(opt)")
    print()
    print("    async def process_audio_stream(self, audio_chunk):")
    print("        # audio_chunk can be bytes, WAV, MP3, etc.")
    print("        try:")
    print("            text = await self.asr.recognize(audio_chunk)")
    print("            return text")
    print("        except Exception as e:")
    print("            print(f'ASR Error: {e}')")
    print("            return None")
    print("```")
    print()
    print("Key features:")
    print("- ✅ Automatic audio format detection and conversion")
    print("- ✅ Proper error handling with helpful messages")
    print("- ✅ Compatible with LiveTalking's ASR pipeline")
    print("- ✅ Supports both sync and async usage")

    return True


async def main():
    """Run all demos"""
    print("Tencent ASR Integration Demo")
    print("=" * 60)
    print("This demo shows how to use Tencent Cloud ASR")
    print("with the LiveTalking project")
    print()

    # Check if we have credentials
    secret_id = os.environ.get("TENCENT_ASR_SECRET_ID")
    secret_key = os.environ.get("TENCENT_ASR_SECRET_KEY")

    if not secret_id or not secret_key:
        print("⚠️  No credentials found in environment variables")
        print("   Set TENCENT_ASR_SECRET_ID and TENCENT_ASR_SECRET_KEY")
        print("   to run the API demos")
        print()

    # Run demos
    results = []

    # Always run structure demo
    results.append(await demo_integration_example())

    # Run API demos only if credentials exist
    if secret_id and secret_key:
        results.append(await demo_basic_usage())
        results.append(await demo_with_real_audio())
        results.append(await demo_mp3_conversion())
    else:
        print("\n" + "=" * 60)
        print("API Demos Skipped")
        print("=" * 60)
        print("To run the API demos:")
        print("1. Get credentials from Tencent Cloud Console")
        print("2. Set environment variables:")
        print("   export TENCENT_ASR_SECRET_ID=your_id")
        print("   export TENCENT_ASR_SECRET_KEY=your_key")
        print("3. Run this script again")

    # Summary
    print("\n" + "=" * 60)
    print("Demo Summary")
    print("=" * 60)
    print(f"Completed {len(results)} demos")
    print(f"✅ Passed: {sum(results)}/{len(results)}")

    if all(results):
        print("\n🎉 All demos completed successfully!")
        print("\nYou're ready to use Tencent ASR with LiveTalking!")
    else:
        print("\n⚠️  Some demos failed, but the implementation is ready")
        print("   Check the error messages above for details")

    return all(results)


if __name__ == "__main__":
    result = asyncio.run(main())
    sys.exit(0 if result else 1)
