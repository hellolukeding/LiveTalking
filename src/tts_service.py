"""
TTS Service Wrapper for Doubao
Provides text-to-speech functionality with voice preview support
"""
import os
import gzip
import uuid
import asyncio
import time
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
DOUBAO_RESOURCE_ID_CANDIDATES = os.getenv("DOUBAO_RESOURCE_ID_CANDIDATES", "")
DOUBAO_API_URL = "wss://openspeech.bytedance.com/api/v3/tts/unidirectional/stream"


def _json_dumps(obj):
    """Simple JSON serialization"""
    import json
    return json.dumps(obj)


def _resolve_resource_candidates() -> list[str]:
    candidates: list[str] = []
    configured = (DOUBAO_RESOURCE_ID or "").strip()
    if configured:
        candidates.append(configured)
    if DOUBAO_RESOURCE_ID_CANDIDATES:
        for item in DOUBAO_RESOURCE_ID_CANDIDATES.split(","):
            item = item.strip()
            if item and item not in candidates:
                candidates.append(item)
    for default_resource in ("volc.service_type.10029", "seed-tts-1.0"):
        if default_resource not in candidates:
            candidates.append(default_resource)
    return candidates


def pcm16le_to_wav_bytes(pcm_bytes: bytes, sample_rate: int = 16000, channels: int = 1) -> bytes:
    if not pcm_bytes:
        return b""
    import io
    import wave

    with io.BytesIO() as buffer:
        with wave.open(buffer, "wb") as wav_file:
            wav_file.setnchannels(channels)
            wav_file.setsampwidth(2)
            wav_file.setframerate(sample_rate)
            wav_file.writeframes(pcm_bytes)
        return buffer.getvalue()


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

    if not all([DOUBAO_APPID, DOUBAO_ACCESS_TOKEN]):
        logger.error("[TTS] Missing Doubao credentials (DOUBAO_APPID, DOUBAO_ACCESS_TOKEN)")
        return None

    try:
        # Run WebSocket connection in executor with timeout
        loop = asyncio.get_event_loop()
        audio_data = await asyncio.wait_for(
            loop.run_in_executor(
                None,
                _sync_generate_audio,
                text,
                voice_id
            ),
            timeout=15.0  # 15 second timeout
        )
        return audio_data

    except asyncio.TimeoutError:
        logger.error("[TTS] Request timeout after 15 seconds")
        return None
    except Exception as e:
        logger.error(f"[TTS] Error: {str(e)}")
        import traceback
        logger.error(f"[TTS] Traceback: {traceback.format_exc()}")
        return None


def _sync_generate_audio(text: str, voice_id: str) -> bytes:
    """Synchronous WebSocket connection for TTS"""
    resource_candidates = _resolve_resource_candidates()
    last_error = None

    for resource_id in resource_candidates:
        ws = None
        try:
            headers = [
                f"X-Api-App-Key: {DOUBAO_APPID}",
                f"X-Api-Access-Key: {DOUBAO_ACCESS_TOKEN}",
                f"X-Api-Resource-Id: {resource_id}",
                f"X-Api-Connect-Id: {str(uuid.uuid4())}",
            ]

            logger.info(f"[TTS] Connecting to Doubao API with voice_id={voice_id}, resource_id={resource_id}")

            ws = websocket.create_connection(
                DOUBAO_API_URL,
                timeout=10,
                header=headers
            )
            logger.info("[TTS] Connected to Doubao API")

            request_json = {
                "user": {"uid": str(uuid.uuid4())},
                "req_params": {
                    "speaker": voice_id,
                    "audio_params": {
                        "format": "pcm",
                        "sample_rate": 24000,
                        "enable_timestamp": False
                    },
                    "text": text,
                },
            }

            header_req = bytearray(b'\x11\x10\x11\x00')
            payload_bytes = _json_dumps(request_json).encode('utf-8')
            payload_bytes = gzip.compress(payload_bytes)

            full_request = bytearray(header_req)
            full_request.extend(len(payload_bytes).to_bytes(4, 'big'))
            full_request.extend(payload_bytes)

            ws.send_binary(bytes(full_request))
            logger.info("[TTS] Request sent, waiting for audio...")

            audio_chunks = []
            total_samples = 0
            max_samples = 24000 * 10
            start_time = time.time()
            max_duration = 10.0

            while total_samples < max_samples and (time.time() - start_time) < max_duration:
                try:
                    ws.settimeout(2.0)
                    result = ws.recv()
                    if len(result) == 0:
                        break

                    header_size = (result[0] & 0x0F) * 4
                    message_type = (result[1] & 0xF0) >> 4
                    payload = result[header_size:]

                    if message_type == 0xb and len(payload) >= 8:
                        audio_data = payload[8:]
                        if len(audio_data) > 0:
                            audio_np = np.frombuffer(audio_data, dtype=np.int16).astype(np.float32) / 32767.0
                            audio_16k = resampy.resample(audio_np, sr_orig=24000, sr_new=16000)
                            audio_16k_int16 = (audio_16k * 32767).astype(np.int16)
                            audio_chunks.append(audio_16k_int16.tobytes())
                            total_samples += len(audio_16k)
                            logger.debug(f"[TTS] Received audio chunk: {len(audio_16k)} samples, total: {total_samples}")
                    elif message_type == 0xc:
                        logger.info("[TTS] Received end-of-stream message")
                        break
                    elif message_type == 0xf:
                        err = ""
                        if len(payload) >= 8:
                            err_payload = payload[8:]
                            try:
                                err_payload = gzip.decompress(err_payload)
                            except Exception:
                                pass
                            err = err_payload.decode("utf-8", errors="ignore")
                        last_error = f"error_response:{err or 'unknown'}"
                        logger.warning(f"[TTS] Doubao error for resource_id={resource_id}: {err}")
                        break

                except websocket.WebSocketTimeoutException:
                    if len(audio_chunks) > 0:
                        logger.info("[TTS] No new data for 2s, stream complete")
                        break
                    continue

            if audio_chunks:
                logger.info(f"[TTS] Success: generated {total_samples} samples ({total_samples/16000:.2f}s)")
                return b''.join(audio_chunks)

            logger.warning(f"[TTS] No audio data received for resource_id={resource_id}")
            last_error = last_error or f"no_audio_resource_{resource_id}"
        except websocket.WebSocketTimeoutException:
            last_error = "websocket_connection_timeout"
            logger.error("[TTS] WebSocket connection timeout")
        except Exception as e:
            last_error = str(e)
            logger.error(f"[TTS] WebSocket error: {str(e)}")
            import traceback
            logger.error(f"[TTS] Traceback: {traceback.format_exc()}")
        finally:
            if ws:
                try:
                    ws.close()
                except Exception:
                    pass

    logger.error(f"[TTS] All resource candidates failed for voice_id={voice_id}, last_error={last_error}")
    return None


async def generate_speech_async(
    text: str,
    voice_id: str = os.getenv("DOUBAO_VOICE_ID", "zh_female_tianxinxiaomei_emo_v2_mars_bigtts")
) -> bytes:
    """
    Generate speech for actual conversation use

    Args:
        text: Text to synthesize
        voice_id: Voice type ID

    Returns:
        Audio data as bytes
    """
    return await generate_preview_audio(text, voice_id)
