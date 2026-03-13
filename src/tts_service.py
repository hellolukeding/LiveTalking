"""
TTS Service Wrapper for Doubao
Provides text-to-speech functionality with voice preview support
"""
import aiohttp
import asyncio
from logger import logger

# Doubao TTS configuration
TTS_SERVER_URL = "http://127.0.0.1:9880"

async def generate_preview_audio(text: str, voice_id: str) -> bytes:
    """
    Generate audio using Doubao TTS for voice preview

    Args:
        text: Text to synthesize
        voice_id: Voice type ID

    Returns:
        Audio data as bytes (mp3 format)
    """
    try:
        async with aiohttp.ClientSession() as session:
            payload = {
                "text": text,
                "voice_type": voice_id,
                "speed": 1.0,
            }

            async with session.post(
                f"{TTS_SERVER_URL}/v1/tts",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=10)
            ) as response:
                if response.status != 200:
                    logger.error(f"[TTS] Request failed: {response.status}")
                    return None

                audio_data = await response.read()
                return audio_data

    except asyncio.TimeoutError:
        logger.error("[TTS] Request timeout")
        return None
    except Exception as e:
        logger.error(f"[TTS] Error: {str(e)}")
        return None


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
