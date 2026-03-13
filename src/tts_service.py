"""
TTS Service Wrapper for Doubao
Provides text-to-speech functionality with voice preview support
"""
import os
import gzip
import uuid
import asyncio
from logger import logger

try:
    import websocket
    import numpy as np
    import resampy
    IMPORTS_OK = True
except ImportError as e:
    logger.error(f"[TTS] Import error: {e}")
    IMPORTS_OK = False

# Doubao TTS configuration - load from environment
DOUBAO_APPID = os.getenv("DOUBAO_APPID")
DOUBAO_ACCESS_TOKEN = os.getenv("DOUBAO_ACCESS_TOKEN") or os.getenv("DOUBAO_AccessKeyID") or os.getenv("DOUBAO_TOKEN")
DOUBAO_RESOURCE_ID = os.getenv("DOUBAO_RESOURCE_ID")
DOUBAO_API_URL = "wss://openspeech.bytedance.com/api/v3/tts/unidirectional/stream"


async def generate_preview_audio(text: str, voice_id: str) -> bytes:
    """
    Generate audio using Doubao TTS for voice preview

    Args:
        text: Text to synthesize
        voice_id: Voice type ID

    Returns:
        Audio data as bytes (PCM 16-bit mono, 16kHz)
    """
    if not IMPORTS_OK:
        logger.error("[TTS] Required imports not available")
        return None

    if not all([DOUBAO_APPID, DOUBAO_ACCESS_TOKEN, DOUBAO_RESOURCE_ID]):
        logger.error("[TTS] Missing Doubao credentials (DOUBAO_APPID, DOUBAO_ACCESS_TOKEN, DOUBAO_RESOURCE_ID)")
        return None

    try:
        # Run WebSocket connection in executor to avoid blocking
        loop = asyncio.get_event_loop()
        audio_data = await loop.run_in_executor(
            None,
            _sync_generate_audio,
            text,
            voice_id
        )
        return audio_data

    except Exception as e:
        logger.error(f"[TTS] Error: {str(e)}")
        return None


def _sync_generate_audio(text: str, voice_id: str) -> bytes:
    """Synchronous WebSocket connection for TTS"""
    try:
        # Build WebSocket headers
        headers = [
            f"X-Api-App-Key: {DOUBAO_APPID}",
            f"X-Api-Access-Key: {DOUBAO_ACCESS_TOKEN}",
            f"X-Api-Resource-Id: {DOUBAO_RESOURCE_ID}",
            f"X-Api-Connect-Id: {str(uuid.uuid4())}",
        ]

        # Connect to Doubao API
        ws = websocket.create_connection(
            DOUBAO_API_URL,
            timeout=10,
            header=headers
        )

        # Build request
        request_json = {
            "user": {"uid": str(uuid.uuid4())},
            "req_params": {
                "speaker": voice_id,
                "audio_params": {
                    "format": "pcm",
                    "sample_rate": 24000,  # API returns 24kHz
                    "enable_timestamp": False
                },
                "text": text,
            },
        }

        # Build binary request format
        header_req = bytearray(b'\x11\x10\x11\x00')
        payload_bytes = json_dumps(request_json).encode('utf-8')
        payload_bytes = gzip.compress(payload_bytes)

        full_request = bytearray(header_req)
        full_request.extend(len(payload_bytes).to_bytes(4, 'big'))
        full_request.extend(payload_bytes)

        ws.send_binary(bytes(full_request))

        # Collect audio chunks
        audio_chunks = []
        total_samples = 0
        max_samples = 24000 * 5  # Max 5 seconds of audio

        while total_samples < max_samples:
            result = ws.recv()
            if len(result) == 0:
                break

            header_size = (result[0] & 0x0F) * 4
            message_type = (result[1] & 0xF0) >> 4
            payload = result[header_size:]

            # Message type 0xb = audio data
            if message_type == 0xb and len(payload) >= 8:
                seq = int.from_bytes(payload[:4], "big")
                size = int.from_bytes(payload[4:8], "big")
                audio_data = payload[8:]

                if len(audio_data) > 0:
                    # Resample from 24kHz to 16kHz
                    audio_np = np.frombuffer(audio_data, dtype=np.int16).astype(np.float32) / 32767.0
                    audio_16k = resampy.resample(audio_np, sr_orig=24000, sr_new=16000)
                    audio_16k_int16 = (audio_16k * 32767).astype(np.int16)

                    audio_chunks.append(audio_16k_int16.tobytes())
                    total_samples += len(audio_16k)

            # Message type 0xc = end of stream
            elif message_type == 0xc:
                break

        ws.close()

        if audio_chunks:
            return b''.join(audio_chunks)
        return None

    except Exception as e:
        logger.error(f"[TTS] WebSocket error: {str(e)}")
        return None


def json_dumps(obj):
    """Simple JSON serialization (avoiding extra import)"""
    import json
    return json.dumps(obj)


async def generate_speech_async(text: str, voice_id: str = "zh_female_wenroushunshun_mars_bigtts") -> bytes:
    """
    Generate speech for actual conversation use

    Args:
        text: Text to synthesize
        voice_id: Voice type ID

    Returns:
        Audio data as bytes
    """
    return await generate_preview_audio(text, voice_id)
