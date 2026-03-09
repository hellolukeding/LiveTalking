###############################################################################
#  Copyright (C) 2024 LiveTalking@lipku https://github.com/lipku/LiveTalking
#  email: lipku@foxmail.com
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.
###############################################################################

import base64
import hashlib
import hmac
import json
import os
import time
import uuid
from datetime import datetime, timezone
from typing import Dict, Optional, Tuple

# Ensure a `logger` is available; prefer project `logger`, otherwise provide a lightweight fallback.
try:
    from logger import logger
except Exception:
    class MockLogger:
        def debug(self, msg, *args):
            print(f"DEBUG:{msg % args if args else msg}")

        def info(self, msg, *args):
            print(f"INFO:{msg % args if args else msg}")

        def warning(self, msg, *args):
            print(f"WARNING:{msg % args if args else msg}")

        def error(self, msg, *args):
            print(f"ERROR:{msg % args if args else msg}")

    logger = MockLogger()


class BaseASR:
    def __init__(self, opt, parent=None):
        self.opt = opt
        self.parent = parent
        self.fps = getattr(opt, 'fps', 30)
        self.sample_rate = 16000
        self.chunk = self.sample_rate // self.fps
        from queue import Queue

        import torch.multiprocessing as mp
        self.queue = Queue()
        self.output_queue = mp.Queue()
        self.batch_size = getattr(opt, 'batch_size', 1)
        self.frames = []
        self.stride_left_size = getattr(opt, 'l', 0)
        self.stride_right_size = getattr(opt, 'r', 0)
        self.feat_queue = mp.Queue(2)

    def flush_talk(self):
        try:
            self.queue.queue.clear()
        except Exception:
            pass

    def put_audio_frame(self, audio_chunk, datainfo: dict):
        self.queue.put((audio_chunk, datainfo))

    def get_audio_frame(self):
        import queue

        import numpy as np

        try:
            frame, eventpoint = self.queue.get(block=True, timeout=0.025)
            type = 0
        except queue.Empty:
            if self.parent and getattr(self.parent, 'curr_state', 0) > 1:
                frame = self.parent.get_audio_stream(self.parent.curr_state)
                type = self.parent.curr_state
            else:
                frame = np.zeros(self.chunk, dtype=np.float32)
                type = 1
            eventpoint = None
        return frame, type, eventpoint

    def get_audio_out(self):
        return self.output_queue.get()

    def warm_up(self):
        for _ in range(self.stride_left_size + self.stride_right_size):
            audio_frame, type, eventpoint = self.get_audio_frame()
            self.frames.append(audio_frame)
            self.output_queue.put((audio_frame, type, eventpoint))
        for _ in range(self.stride_left_size):
            self.output_queue.get()

    def run_step(self):
        pass

    def get_next_feat(self, block, timeout):
        return self.feat_queue.get(block, timeout)

    class MockLogger:
        def debug(
            self, msg, *args): print(f"DEBUG: {msg % args if args else msg}")

        def info(
            self, msg, *args): print(f"INFO: {msg % args if args else msg}")

        def warning(
            self, msg, *args): print(f"WARNING: {msg % args if args else msg}")
        def error(
            self, msg, *args): print(f"ERROR: {msg % args if args else msg}")

    logger = MockLogger()


class TencentApiAsr(BaseASR):
    """
    Tencent Cloud ASR Implementation
    Uses Tencent Cloud's Sentence Recognition API for speech-to-text
    """

    def __init__(self, opt, parent=None):
        super().__init__(opt, parent)
        self._url = "https://asr.tencentcloudapi.com"
        self._secret_id = None
        self._secret_key = None
        self._engine_model_type = "16k_zh"
        self._channel_num = 1
        self._speaker_diarization = 0
        self._speaker_number = 0
        self._callback_url = ""

        # Load credentials
        self._load_credentials()

    def _load_credentials(self):
        """Load Tencent Cloud credentials from environment variables"""
        # Support both correct and commonly misspelled env var names
        self._secret_id = os.environ.get(
            "TENCENT_ASR_SECRET_ID") or os.environ.get("TENCENT_ASR_SECERET_ID")
        self._secret_key = os.environ.get(
            "TENCENT_ASR_SECRET_KEY") or os.environ.get("TENCENT_ASR_SECERET_KEY")

        if not self._secret_id or not self._secret_key:
            logger.error("[ASR] Tencent ASR secret_id/secret_key not provided")
            raise RuntimeError(
                "Tencent ASR secret_id/secret_key not provided. "
                "Please set TENCENT_ASR_SECRET_ID and TENCENT_ASR_SECRET_KEY environment variables. "
                "You can get these credentials from https://console.cloud.tencent.com/cam/capi"
            )

        # Remove any whitespace
        self._secret_id = self._secret_id.strip()
        self._secret_key = self._secret_key.strip()

        if not self._secret_id or not self._secret_key:
            logger.error(
                "[ASR] Tencent ASR secret_id/secret_key cannot be empty")
            raise RuntimeError(
                "Tencent ASR secret_id/secret_key cannot be empty")

        logger.debug(
            f"[ASR] Using Tencent ASR with secret_id: {self._secret_id[:8]}...")

    def _sign(self, key, msg: str):
        """Generate HMAC-SHA256 signature"""
        return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()

    def _build_request(self, audio_data: str) -> Tuple[Dict, str]:
        """Build Tencent ASR API request headers and payload"""
        service = "asr"
        host = "asr.tencentcloudapi.com"
        version = "2019-06-14"
        action = "SentenceRecognition"
        algorithm = "TC3-HMAC-SHA256"
        timestamp = int(time.time())
        date = datetime.fromtimestamp(
            timestamp, timezone.utc).strftime("%Y-%m-%d")

        # Build request parameters
        params = {
            "ProjectId": 0,
            "SubServiceType": 2,
            "EngSerViceType": self._engine_model_type,
            "SourceType": 1,
            "VoiceFormat": "wav",
            "UsrAudioKey": str(uuid.uuid4()),
            "Data": audio_data,
            "DataLen": len(base64.b64decode(audio_data)),
        }

        # For TC3 signing, POST requests include parameters in the payload
        canonical_querystring = ""
        payload = json.dumps(params, separators=(',', ':'), ensure_ascii=False)
        canonical_headers = f"content-type:application/json\nhost:{host}\n"
        signed_headers = "content-type;host"
        hashed_request_payload = hashlib.sha256(
            payload.encode("utf-8")).hexdigest()
        canonical_request = f"POST\n/\n{canonical_querystring}\n{canonical_headers}\n{signed_headers}\n{hashed_request_payload}"
        credential_scope = f"{date}/{service}/tc3_request"
        hashed_canonical_request = hashlib.sha256(
            canonical_request.encode("utf-8")).hexdigest()
        string_to_sign = f"{algorithm}\n{timestamp}\n{credential_scope}\n{hashed_canonical_request}"

        # Generate signature
        secret_date = self._sign(
            ("TC3" + self._secret_key).encode("utf-8"), date)
        secret_service = self._sign(secret_date, service)
        secret_signing = self._sign(secret_service, "tc3_request")
        signature = hmac.new(secret_signing, string_to_sign.encode(
            "utf-8"), hashlib.sha256).hexdigest()

        # Build authorization header
        authorization = f"{algorithm} Credential={self._secret_id}/{credential_scope}, SignedHeaders={signed_headers}, Signature={signature}"

        headers = {
            "Authorization": authorization,
            "Content-Type": "application/json",
            "Host": host,
            "X-TC-Action": action,
            "X-TC-Timestamp": str(timestamp),
            "X-TC-Version": version,
            "X-TC-Region": "ap-beijing"
        }

        logger.debug(
            f"[ASR] Tencent request params keys: {list(params.keys())}")
        return headers, payload

    def _convert_audio_format(self, audio_bytes: bytes) -> bytes:
        """Convert audio to WAV format if needed"""
        # Check if it's already WAV
        def _is_wav(b: bytes) -> bool:
            return len(b) >= 12 and b[0:4] == b"RIFF" and b[8:12] == b"WAVE"

        def _is_mp3(b: bytes) -> bool:
            return len(b) >= 3 and (b[0:3] == b"ID3" or (b[0] == 0xFF and (b[1] & 0xE0) == 0xE0))

        if _is_mp3(audio_bytes):
            logger.debug(
                "[ASR] Detected MP3 input; converting to WAV for Tencent ASR")
            try:
                from io import BytesIO

                from pydub import AudioSegment

                audio = AudioSegment.from_mp3(BytesIO(audio_bytes))
                audio = audio.set_frame_rate(16000).set_channels(1)
                out = BytesIO()
                audio.export(out, format="wav")
                wav_bytes = out.getvalue()
                logger.debug(
                    f"[ASR] Converted MP3 -> WAV, size={len(wav_bytes)} bytes")
                return wav_bytes
            except Exception as e:
                logger.error(
                    f"[ASR] Failed to convert MP3 to WAV: {e}", exc_info=True)
                raise RuntimeError(
                    f"Failed to convert MP3 to WAV for Tencent ASR: {str(e)}")
        elif _is_wav(audio_bytes):
            # Ensure WAV is 16k mono as Tencent expects
            try:
                from io import BytesIO

                from pydub import AudioSegment

                audio = AudioSegment.from_wav(BytesIO(audio_bytes))
                needs_conversion = (audio.frame_rate != 16000) or (
                    audio.channels != 1)
                if needs_conversion:
                    logger.debug(
                        f"[ASR] WAV resample/convert required: frame_rate={audio.frame_rate}, channels={audio.channels}")
                    audio = audio.set_frame_rate(16000).set_channels(1)
                    out = BytesIO()
                    audio.export(out, format="wav")
                    wav_bytes = out.getvalue()
                    logger.debug(
                        f"[ASR] Converted WAV to 16k mono, size={len(wav_bytes)} bytes")
                    return wav_bytes
                else:
                    logger.debug("[ASR] Detected WAV input; sending as-is")
                    return audio_bytes
            except Exception as e:
                logger.warning(
                    f"[ASR] Failed to inspect/convert WAV input: {e}; will send as-is")
                return audio_bytes
        else:
            logger.warning(
                "[ASR] Unknown audio format detected; Tencent ASR may reject the audio")
            return audio_bytes

    def _pcm_to_wav_bytes(self, audio_array, sample_rate: int = 16000) -> bytes:
        """
        Fast helper: convert 1-D numpy array of float32 or int16 PCM samples to WAV bytes (16kHz mono).
        This avoids expensive pydub/soundfile conversions when we already have raw PCM samples.
        """
        try:
            import io
            import wave

            import numpy as _np

            # Ensure numpy array
            if not hasattr(audio_array, 'dtype'):
                # fallback: assume bytes already
                return audio_array

            arr = audio_array
            # If float, convert to int16
            if _np.issubdtype(arr.dtype, _np.floating):
                int16 = _np.clip(arr * 32767, -32768, 32767).astype(_np.int16)
            else:
                int16 = arr.astype(_np.int16)

            buf = io.BytesIO()
            with wave.open(buf, 'wb') as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(sample_rate)
                wf.writeframes(int16.tobytes())

            return buf.getvalue()
        except Exception as e:
            logger.warning(
                f"[ASR] Fast PCM->WAV conversion failed: {e}; falling back to sending raw bytes")
            return audio_array

    async def recognize(self, audio_data: bytes) -> str:
        """
        Recognize speech from audio data

        Args:
            audio_data: Audio data in bytes (can be MP3, WAV, or other formats)

        Returns:
            str: Recognized text

        Raises:
            RuntimeError: If recognition fails or credentials are invalid
        """
        # Convert input into WAV bytes and base64-encode
        try:
            # Fast path: if caller passed raw PCM numpy array or list/tuple, convert directly
            import numpy as _np
            if hasattr(audio_data, 'dtype') or isinstance(audio_data, (list, tuple)):
                wav_bytes = self._pcm_to_wav_bytes(
                    _np.array(audio_data, dtype=_np.float32), 16000)
            else:
                # Otherwise use existing converter which handles mp3/wav/raw bytes
                wav_bytes = self._convert_audio_format(audio_data)

            audio_base64 = base64.b64encode(wav_bytes).decode("utf-8")
        except Exception as e:
            logger.error(
                f"[ASR] Failed to encode audio data: {e}", exc_info=True)
            raise RuntimeError(f"Failed to encode audio data: {str(e)}")

        # Build request
        headers, payload = self._build_request(audio_base64)

        # Send request
        try:
            import httpx

            max_retries = int(os.getenv('TENCENT_ASR_RETRIES', '2'))
            backoff_base = float(os.getenv('TENCENT_ASR_BACKOFF', '0.5'))
            response = None
            last_exc = None
            async with httpx.AsyncClient() as client:
                timeout_seconds = float(
                    os.getenv('TENCENT_ASR_TIMEOUT', '8.0'))
                for attempt in range(1, max_retries + 1):
                    try:
                        response = await client.post(self._url, headers=headers, data=payload, timeout=timeout_seconds)
                        # Treat 5xx as transient and retryable
                        if response.status_code >= 500:
                            last_exc = RuntimeError(
                                f"Server error: {response.status_code}")
                            raise httpx.RequestError(str(last_exc))
                        break
                    except (httpx.RequestError, httpx.TimeoutException) as e:
                        last_exc = e
                        logger.warning(
                            f"[ASR] Tencent request attempt {attempt}/{max_retries} failed: {e}")
                        if attempt == max_retries:
                            raise
                        await asyncio.sleep(backoff_base * (2 ** (attempt - 1)))

            logger.debug(
                f"[ASR] Tencent API response status: {response.status_code}")

            if response.status_code != 200:
                logger.error(
                    f"[ASR] Tencent ASR API error: {response.status_code}, response: {response.text}")
                raise RuntimeError(
                    f"Tencent ASR API error: {response.status_code}, response: {response.text}")

            result = response.json()
            logger.debug(
                f"[ASR] Tencent API response keys: {list(result.keys())}")

            # Tencent API may wrap result in a top-level "Response" object
            # or return fields at the top-level in some variants. Accept both.
            if "Response" in result and isinstance(result["Response"], dict):
                response_body = result["Response"]
            else:
                response_body = result

            # Check for errors
            if "Error" in response_body:
                error_msg = response_body['Error']['Message']
                error_code = response_body['Error']['Code']
                logger.error(
                    f"[ASR] Tencent ASR error - Code: {error_code}, Message: {error_msg}")

                if error_code == "AuthFailure.SecretIdNotFound":
                    raise RuntimeError(
                        f"Tencent ASR authentication failed: SecretId not found. Please check that your TENCENT_ASR_SECRET_ID is correct. Error: {error_msg}")
                elif error_code == "AuthFailure.SignatureFailure":
                    raise RuntimeError(
                        f"Tencent ASR authentication failed: Signature validation failed. Please check that your TENCENT_ASR_SECRET_KEY is correct. Error: {error_msg}")
                elif error_code == "InvalidParameterValue.ErrorInvalidVoicedata":
                    raise RuntimeError(
                        f"Tencent ASR audio format error: {error_msg}. Ensure the audio is a PCM WAV (16kHz mono) or provide compatible audio.")
                else:
                    raise RuntimeError(
                        f"Tencent ASR API error - Code: {error_code}, Message: {error_msg}")

            # Extract transcript. Tencent may return various keys depending on API/version.
            transcript = None
            # Common string fields — accept empty string too (silence)
            for key in ("Result", "Text", "Transcript", "TextResult"):
                val = response_body.get(key)
                if isinstance(val, str):
                    transcript = val
                    break

            # Some responses include a WordList (detailed words). Join them if present.
            if transcript is None and isinstance(response_body.get("WordList"), list):
                try:
                    words = []
                    for w in response_body.get("WordList", []):
                        if isinstance(w, dict):
                            # Tencent may provide 'Word' or 'Text'
                            word_text = w.get("Word") or w.get(
                                "Text") or w.get("WordStr")
                            if word_text:
                                words.append(word_text)
                        elif isinstance(w, str):
                            words.append(w)
                    transcript = "".join(words)
                except Exception:
                    transcript = None

            # Handle async response
            if transcript is None:
                if "TaskId" in response_body:
                    task_id = response_body.get("TaskId")
                    logger.error(
                        f"[ASR] Tencent returned TaskId for async job: {task_id}. Full response: {response_body}")
                    raise RuntimeError(
                        f"Tencent ASR returned an async TaskId (TaskId={task_id}). This API path expects synchronous results. Consider using smaller audio.")

                logger.error(
                    f"[ASR] Tencent API response missing transcript keys, response keys: {list(response_body.keys())}")
                raise RuntimeError(
                    f"Tencent API response missing expected transcript field. Response keys: {list(response_body.keys())}")

            logger.debug(f"[ASR] Tencent ASR recognized: {transcript}")
            return transcript

        except Exception as e:
            logger.error(
                f"[ASR] Failed to recognize speech with Tencent ASR: {str(e)}", exc_info=True)
            raise RuntimeError(
                f"Failed to recognize speech with Tencent ASR: {str(e)}")

    def run_step(self):
        """
        Process audio frames and put results to output queue
        This method is called by the ASR pipeline
        """
        try:
            # Get audio frame
            audio_frame, type, eventpoint = self.get_audio_frame()

            # For ASR, we need to accumulate audio frames and process them
            # This is a simplified version - in practice, you'd want to accumulate
            # more audio before making API calls

            # For now, just pass through the audio frame
            self.output_queue.put((audio_frame, type, eventpoint))

        except Exception as e:
            logger.error(f"[ASR] Error in run_step: {e}", exc_info=True)
            # Put empty frame to avoid blocking
            import numpy as np
            frame = np.zeros(self.chunk, dtype=np.float32)
            self.output_queue.put((frame, 1, None))


# For backward compatibility with the reference code structure
class TencentApiAsrLegacy:
    """
    Legacy interface compatible with the reference code
    Uses AudioMessage and TextMessage protocol
    """

    def __init__(self):
        self._url = "https://asr.tencentcloudapi.com"
        self._secret_id = None
        self._secret_key = None
        self._engine_model_type = "16k_zh"
        self._channel_num = 1
        self._speaker_diarization = 0
        self._speaker_number = 0
        self._callback_url = ""

        # Load credentials
        self._load_credentials()

    def setup(self):
        """Setup method for compatibility"""
        pass

    def _load_credentials(self):
        """Load credentials from environment"""
        self._secret_id = os.environ.get(
            "TENCENT_ASR_SECRET_ID") or os.environ.get("TENCENT_ASR_SECERET_ID")
        self._secret_key = os.environ.get(
            "TENCENT_ASR_SECRET_KEY") or os.environ.get("TENCENT_ASR_SECERET_KEY")

        if not self._secret_id or not self._secret_key:
            raise RuntimeError("Tencent ASR credentials not provided")

        self._secret_id = self._secret_id.strip()
        self._secret_key = self._secret_key.strip()

    def _sign(self, key, msg: str):
        return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()

    def _build_request(self, audio_data: str) -> Tuple[Dict, str]:
        """Build request - same as above"""
        service = "asr"
        host = "asr.tencentcloudapi.com"
        version = "2019-06-14"
        action = "SentenceRecognition"
        algorithm = "TC3-HMAC-SHA256"
        timestamp = int(time.time())
        date = datetime.fromtimestamp(
            timestamp, timezone.utc).strftime("%Y-%m-%d")

        params = {
            "ProjectId": 0,
            "SubServiceType": 2,
            "EngSerViceType": self._engine_model_type,
            "SourceType": 1,
            "VoiceFormat": "wav",
            "UsrAudioKey": str(uuid.uuid4()),
            "Data": audio_data,
            "DataLen": len(base64.b64decode(audio_data)),
        }

        canonical_querystring = ""
        payload = json.dumps(params, separators=(',', ':'), ensure_ascii=False)
        canonical_headers = f"content-type:application/json\nhost:{host}\n"
        signed_headers = "content-type;host"
        hashed_request_payload = hashlib.sha256(
            payload.encode("utf-8")).hexdigest()
        canonical_request = f"POST\n/\n{canonical_querystring}\n{canonical_headers}\n{signed_headers}\n{hashed_request_payload}"
        credential_scope = f"{date}/{service}/tc3_request"
        hashed_canonical_request = hashlib.sha256(
            canonical_request.encode("utf-8")).hexdigest()
        string_to_sign = f"{algorithm}\n{timestamp}\n{credential_scope}\n{hashed_canonical_request}"

        secret_date = self._sign(
            ("TC3" + self._secret_key).encode("utf-8"), date)
        secret_service = self._sign(secret_date, service)
        secret_signing = self._sign(secret_service, "tc3_request")
        signature = hmac.new(secret_signing, string_to_sign.encode(
            "utf-8"), hashlib.sha256).hexdigest()

        authorization = f"{algorithm} Credential={self._secret_id}/{credential_scope}, SignedHeaders={signed_headers}, Signature={signature}"

        headers = {
            "Authorization": authorization,
            "Content-Type": "application/json",
            "Host": host,
            "X-TC-Action": action,
            "X-TC-Timestamp": str(timestamp),
            "X-TC-Version": version,
            "X-TC-Region": "ap-beijing"
        }

        return headers, payload

    async def run(self, input_data, **kwargs) -> str:
        """
        Main entry point compatible with reference code
        Args:
            input_data: Audio data (bytes) or AudioMessage object
            **kwargs: Additional parameters

        Returns:
            str: Recognized text
        """
        # Handle input data
        if hasattr(input_data, 'data'):
            audio_data = input_data.data
        else:
            audio_data = input_data

        # Fast path: accept numpy arrays or lists and convert to WAV bytes
        try:
            import numpy as _np
            if hasattr(audio_data, 'dtype') or isinstance(audio_data, (list, tuple)):
                wav_bytes = self._convert_audio_format(self._pcm_to_wav_bytes(
                    _np.array(audio_data, dtype=_np.float32), 16000))
                audio_base64 = base64.b64encode(wav_bytes).decode("utf-8")
            elif isinstance(audio_data, bytes):
                audio_bytes = self._convert_audio_format(audio_data)
                audio_base64 = base64.b64encode(audio_bytes).decode("utf-8")
            elif isinstance(audio_data, str):
                # Assume it's already base64
                audio_base64 = audio_data
            else:
                raise RuntimeError(
                    f"Unsupported input data type: {type(audio_data)}")
        except Exception:
            # Fallback to previous behavior
            if isinstance(audio_data, bytes):
                audio_bytes = self._convert_audio_format(audio_data)
                audio_base64 = base64.b64encode(audio_bytes).decode("utf-8")
            elif isinstance(audio_data, str):
                audio_base64 = audio_data
            else:
                raise

        # Build and send request
        headers, payload = self._build_request(audio_base64)

        try:
            import httpx
            async with httpx.AsyncClient() as client:
                response = await client.post(self._url, headers=headers, data=payload, timeout=10.0)

                if response.status_code != 200:
                    raise RuntimeError(
                        f"Tencent ASR API error: {response.status_code}, response: {response.text}")

                result = response.json()

                if "Response" not in result:
                    raise RuntimeError(
                        f"Unexpected Tencent API response format: {result}")

                response_body = result["Response"]

                if "Error" in response_body:
                    error_msg = response_body['Error']['Message']
                    error_code = response_body['Error']['Code']
                    raise RuntimeError(
                        f"Tencent ASR error - Code: {error_code}, Message: {error_msg}")

                # Extract transcript
                transcript = None
                if isinstance(response_body.get("Result"), str) and response_body.get("Result"):
                    transcript = response_body.get("Result")

                if not transcript:
                    for alt_key in ("Text", "Transcript", "TextResult"):
                        if isinstance(response_body.get(alt_key), str) and response_body.get(alt_key):
                            transcript = response_body.get(alt_key)
                            break

                if not transcript:
                    raise RuntimeError("No transcript found in response")

                return transcript

        except Exception as e:
            logger.error(
                f"[ASR] Failed to recognize speech: {str(e)}", exc_info=True)
            raise RuntimeError(
                f"Failed to recognize speech with Tencent ASR: {str(e)}")

    def _convert_audio_format(self, audio_bytes: bytes) -> bytes:
        """Convert audio to WAV format if needed"""
        def _is_wav(b: bytes) -> bool:
            return len(b) >= 12 and b[0:4] == b"RIFF" and b[8:12] == b"WAVE"

        def _is_mp3(b: bytes) -> bool:
            return len(b) >= 3 and (b[0:3] == b"ID3" or (b[0] == 0xFF and (b[1] & 0xE0) == 0xE0))

        if _is_mp3(audio_bytes):
            try:
                from io import BytesIO

                from pydub import AudioSegment

                audio = AudioSegment.from_mp3(BytesIO(audio_bytes))
                audio = audio.set_frame_rate(16000).set_channels(1)
                out = BytesIO()
                audio.export(out, format="wav")
                return out.getvalue()
            except Exception as e:
                raise RuntimeError(f"Failed to convert MP3 to WAV: {str(e)}")
        elif _is_wav(audio_bytes):
            try:
                from io import BytesIO

                from pydub import AudioSegment

                audio = AudioSegment.from_wav(BytesIO(audio_bytes))
                needs_conversion = (audio.frame_rate != 16000) or (
                    audio.channels != 1)
                if needs_conversion:
                    audio = audio.set_frame_rate(16000).set_channels(1)
                    out = BytesIO()
                    audio.export(out, format="wav")
                    return out.getvalue()
                else:
                    return audio_bytes
            except Exception as e:
                return audio_bytes
        else:
            return audio_bytes


# Register with the system (if applicable)
try:
    from ..builder import ASREngines
    ASREngines.register("Tencent-API")(TencentApiAsr)
except ImportError:
    # If the builder module doesn't exist, skip registration
    pass
