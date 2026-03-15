import asyncio
import logging
import os
import time
from dataclasses import dataclass
from typing import Any, Optional

import numpy as np

logger = logging.getLogger(__name__)


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except Exception:
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except Exception:
        return default


def _env_bool(name: str, default: bool) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


def _to_mono_float32(samples: np.ndarray) -> np.ndarray:
    arr = samples
    if arr is None:
        return np.zeros((0,), dtype=np.float32)
    if arr.ndim > 1:
        arr = arr[:, 0]
    if arr.dtype == np.int16:
        arr = (arr.astype(np.float32) / 32768.0)
    else:
        arr = arr.astype(np.float32, copy=False)
        # Heuristic: some callers pass int16 casted to float32 without normalization
        if np.max(np.abs(arr)) > 1.5:
            arr = arr / 32768.0
    return arr


@dataclass
class VADConfig:
    sample_rate_out: int = 16000
    # VAD thresholds are RMS in [0,1]. Defaults bias slightly towards sensitivity;
    # a noise-adaptive floor (below) helps avoid false triggers in noisy rooms.
    rms_speech: float = 0.006
    rms_barge_in: float = 0.010
    end_silence_ms: int = 400
    min_utterance_ms: int = 350
    max_utterance_ms: int = 8000
    cooldown_ms: int = 500
    dedup_window_ms: int = 3000
    barge_in_ms: int = 120
    barge_in_preroll_ms: int = 320
    enable_orchestrator: bool = True
    noise_adapt: bool = True
    noise_alpha: float = 0.05
    noise_multiplier: float = 3.0
    noise_margin: float = 0.0015
    debug_rms: bool = False

    @classmethod
    def from_env(cls) -> "VADConfig":
        return cls(
            sample_rate_out=_env_int("ORCH_ASR_SR", 16000),
            rms_speech=_env_float("ORCH_VAD_RMS_SPEECH", 0.006),
            rms_barge_in=_env_float("ORCH_VAD_RMS_BARGE_IN", 0.010),
            end_silence_ms=_env_int("ORCH_VAD_END_SILENCE_MS", 400),
            min_utterance_ms=_env_int("ORCH_VAD_MIN_UTTERANCE_MS", 350),
            max_utterance_ms=_env_int("ORCH_VAD_MAX_UTTERANCE_MS", 8000),
            cooldown_ms=_env_int("ORCH_ASR_COOLDOWN_MS", 500),
            dedup_window_ms=_env_int("ORCH_ASR_DEDUP_WINDOW_MS", 3000),
            barge_in_ms=_env_int("ORCH_BARGE_IN_MS", 120),
            barge_in_preroll_ms=_env_int("ORCH_BARGE_IN_PREROLL_MS", 320),
            enable_orchestrator=_env_bool("ORCH_ENABLED", True),
            noise_adapt=_env_bool("ORCH_VAD_NOISE_ADAPT", True),
            noise_alpha=_env_float("ORCH_VAD_NOISE_ALPHA", 0.05),
            noise_multiplier=_env_float("ORCH_VAD_NOISE_MULT", 3.0),
            noise_margin=_env_float("ORCH_VAD_NOISE_MARGIN", 0.0015),
            debug_rms=_env_bool("ORCH_VAD_DEBUG", False),
        )


class _TurnAwareNerfreal:
    """
    Wrapper passed to llm_response() so we can safely discard output from cancelled turns.
    llm_response only needs put_msg_txt() and may call it frequently.
    """

    def __init__(self, orchestrator: "ConversationOrchestrator", turn_id: int):
        self._orch = orchestrator
        self._turn_id = turn_id

    def put_msg_txt(self, msg: str, datainfo: dict = {}):  # noqa: B006
        if not self._orch.is_turn_active(self._turn_id):
            return
        self._orch.say(msg, datainfo)


class ConversationOrchestrator:
    """
    ASR -> LLM -> TTS orchestration with:
    - VAD endpointing (one ASR per utterance)
    - single-flight turns with cancellation/discard via turn_id
    - barge-in: user speech interrupts current TTS immediately
    """

    def __init__(self, session_id: int, nerfreal: Any, opt: Any, avatar_name: str = "小助手"):
        self.session_id = session_id
        self.nerfreal = nerfreal
        self.opt = opt
        self.avatar_name = avatar_name

        self.cfg = VADConfig.from_env()

        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._datachannel = None

        self._turn_id = 0
        self._turn_lock = asyncio.Lock()

        self._last_asr_time = 0.0
        self._last_asr_text: Optional[str] = None
        self._last_asr_text_time = 0.0

        self._in_speech = False
        self._speech_started_time: Optional[float] = None
        self._last_voice_time: Optional[float] = None
        self._utterance_buf: list[np.ndarray] = []
        self._utterance_sr: Optional[int] = None

        self._barge_in_started_time: Optional[float] = None
        self._barge_in_audio_buf: list[np.ndarray] = []
        self._barge_in_sr: Optional[int] = None
        self._barge_in_buf_samples = 0

        self._noise_rms: Optional[float] = None
        self._last_debug_time = 0.0

        self._asr = None
        try:
            from tencentasr import TencentApiAsr

            self._asr = TencentApiAsr(opt=self.opt, parent=None)
        except Exception as e:
            logger.warning(f"[ORCH-{session_id}] Tencent ASR unavailable: {e}")
            self._asr = None

    def set_datachannel(self, channel, loop: asyncio.AbstractEventLoop):
        self._datachannel = channel
        self._loop = loop

    def is_turn_active(self, turn_id: int) -> bool:
        return turn_id == self._turn_id

    def _send_custom_msg(self, msg: str):
        ch = self._datachannel
        if not ch:
            return
        try:
            if ch.readyState != "open":
                return
        except Exception:
            return
        loop = self._loop
        try:
            if loop and loop.is_running():
                loop.call_soon_threadsafe(ch.send, msg)
            else:
                ch.send(msg)
        except Exception:
            pass

    def interrupt(self):
        try:
            if hasattr(self.nerfreal, "flush_talk"):
                self.nerfreal.flush_talk()
        except Exception:
            pass

    def say(self, msg: str, datainfo: dict = {}):  # noqa: B006
        try:
            if hasattr(self.nerfreal, "put_msg_txt"):
                self.nerfreal.put_msg_txt(msg, datainfo)
        except Exception:
            pass

    def _is_tts_speaking(self) -> bool:
        try:
            if hasattr(self.nerfreal, "is_speaking"):
                return bool(self.nerfreal.is_speaking())
        except Exception:
            return False
        return False

    def ingest_audio(self, samples: np.ndarray, sample_rate: Optional[int]):
        if not self.cfg.enable_orchestrator:
            return

        sr = int(sample_rate or 16000)
        mono = _to_mono_float32(samples)
        if mono.size == 0:
            return

        now = time.perf_counter()
        rms = float(np.sqrt(np.mean(np.square(mono))) + 1e-12)

        speaking = self._is_tts_speaking()

        base_thr_speech = float(self.cfg.rms_speech)

        # Update a simple noise-floor estimate only from quiet frames (below base threshold).
        # If the first audio we ever see is speech, we intentionally keep noise floor unset so VAD remains sensitive.
        if self.cfg.noise_adapt and (not speaking) and (not self._in_speech) and rms < base_thr_speech:
            if self._noise_rms is None:
                self._noise_rms = rms
            else:
                alpha = float(self.cfg.noise_alpha)
                self._noise_rms = (1.0 - alpha) * self._noise_rms + alpha * rms

        # Compute dynamic thresholds (only if we have a learned noise floor).
        thr_speech = base_thr_speech
        thr_barge = float(self.cfg.rms_barge_in)
        if self.cfg.noise_adapt and self._noise_rms is not None:
            floor = float(self._noise_rms)
            thr_speech = max(thr_speech, floor * float(self.cfg.noise_multiplier) + float(self.cfg.noise_margin))
            thr_barge = max(thr_barge, thr_speech * 1.6)

        if self.cfg.debug_rms and (now - self._last_debug_time) >= 1.0:
            self._last_debug_time = now
            logger.info(
                f"[ORCH-{self.session_id}] rms={rms:.4f} thr_speech={thr_speech:.4f} thr_barge={thr_barge:.4f} "
                f"noise={None if self._noise_rms is None else f'{self._noise_rms:.4f}'} "
                f"in_speech={self._in_speech} tts={speaking}"
            )

        if speaking:
            # While TTS is speaking, ignore mic audio unless barge-in is detected.
            if rms >= thr_barge:
                if self._barge_in_started_time is None:
                    self._barge_in_started_time = now
                    self._barge_in_audio_buf = []
                    self._barge_in_sr = sr
                    self._barge_in_buf_samples = 0
                self._append_barge_in_audio(mono, sr)
                if (now - self._barge_in_started_time) * 1000.0 >= self.cfg.barge_in_ms:
                    logger.info(f"[ORCH-{self.session_id}] Barge-in detected (rms={rms:.4f})")
                    self._start_new_turn(interrupt=True)
                    # Start capturing utterance and include pre-trigger audio so short phrases are not lost.
                    self._begin_speech(now, sr)
                    if self._barge_in_audio_buf:
                        for segment in self._barge_in_audio_buf:
                            self._append_audio(segment, sr)
                    else:
                        self._append_audio(mono, sr)
                    self._reset_barge_in_state()
            else:
                self._reset_barge_in_state()
            return

        self._reset_barge_in_state()

        is_voice = rms >= thr_speech
        if is_voice:
            if not self._in_speech:
                self._begin_speech(now, sr)
            self._append_audio(mono, sr)
            self._last_voice_time = now
            return

        # Silence handling: endpoint if we were in speech and silence lasts long enough
        if self._in_speech and self._last_voice_time is not None:
            silence_ms = (now - self._last_voice_time) * 1000.0
            if silence_ms >= self.cfg.end_silence_ms:
                self._finalize_utterance(now)

    def _begin_speech(self, now: float, sr: int):
        self._in_speech = True
        self._speech_started_time = now
        self._last_voice_time = now
        self._utterance_buf = []
        self._utterance_sr = sr

    def _reset_barge_in_state(self):
        self._barge_in_started_time = None
        self._barge_in_audio_buf = []
        self._barge_in_sr = None
        self._barge_in_buf_samples = 0

    def _append_barge_in_audio(self, mono: np.ndarray, sr: int):
        if self._barge_in_sr is None:
            self._barge_in_sr = sr
        if sr != self._barge_in_sr:
            self._barge_in_audio_buf = []
            self._barge_in_buf_samples = 0
            self._barge_in_sr = sr

        segment = mono.copy()
        self._barge_in_audio_buf.append(segment)
        self._barge_in_buf_samples += int(segment.size)

        # Keep only a bounded pre-roll window.
        max_samples = int(max(1, sr * (self.cfg.barge_in_preroll_ms / 1000.0)))
        while self._barge_in_buf_samples > max_samples and self._barge_in_audio_buf:
            removed = self._barge_in_audio_buf.pop(0)
            self._barge_in_buf_samples -= int(removed.size)

    def _append_audio(self, mono: np.ndarray, sr: int):
        if self._utterance_sr is None:
            self._utterance_sr = sr
        # If sample rate changes mid-utterance, finalize and restart (rare)
        if sr != self._utterance_sr:
            self._finalize_utterance(time.perf_counter())
            self._begin_speech(time.perf_counter(), sr)
        self._utterance_buf.append(mono.copy())

        if self._speech_started_time is not None:
            dur_ms = (time.perf_counter() - self._speech_started_time) * 1000.0
            if dur_ms >= self.cfg.max_utterance_ms:
                self._finalize_utterance(time.perf_counter())

    def _finalize_utterance(self, now: float):
        if not self._utterance_buf or self._utterance_sr is None:
            self._reset_speech_state()
            return

        sr = int(self._utterance_sr)
        audio = np.concatenate(self._utterance_buf, axis=0)
        dur_ms = (audio.shape[0] / float(sr)) * 1000.0

        self._reset_speech_state()

        if dur_ms < self.cfg.min_utterance_ms:
            logger.debug(
                f"[ORCH-{self.session_id}] Drop utterance: too short {dur_ms:.0f}ms < {self.cfg.min_utterance_ms}ms"
            )
            return

        # Cooldown to avoid rapid repeat triggers
        cooldown_elapsed_ms = (time.perf_counter() - self._last_asr_time) * 1000.0
        if cooldown_elapsed_ms < self.cfg.cooldown_ms:
            logger.debug(
                f"[ORCH-{self.session_id}] Drop utterance: cooldown {cooldown_elapsed_ms:.0f}ms < {self.cfg.cooldown_ms}ms"
            )
            return

        self._last_asr_time = time.perf_counter()
        self._start_new_turn(interrupt=False)
        turn_id = self._turn_id
        logger.info(f"[ORCH-{self.session_id}] Utterance finalized: {dur_ms:.0f}ms turn={turn_id}")

        if self._loop and self._loop.is_running():
            asyncio.run_coroutine_threadsafe(self._run_turn(turn_id, audio, sr), self._loop)
        else:
            # Fallback: schedule on current running loop if available
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(self._run_turn(turn_id, audio, sr))
            except Exception:
                # Last resort: start a background loop
                import threading

                def _bg():
                    asyncio.run(self._run_turn(turn_id, audio, sr))

                threading.Thread(target=_bg, daemon=True).start()

    def _reset_speech_state(self):
        self._in_speech = False
        self._speech_started_time = None
        self._last_voice_time = None
        self._utterance_buf = []
        self._utterance_sr = None

    def _start_new_turn(self, interrupt: bool):
        # Increment turn id and optionally barge-in interrupt current playback
        self._turn_id += 1
        if interrupt:
            self.interrupt()

    async def _run_turn(self, turn_id: int, audio: np.ndarray, sr_in: int):
        if not self.is_turn_active(turn_id):
            return

        # Resample to 16k mono
        try:
            import resampy  # optional dependency for ASR path
        except Exception as e:
            logger.warning(f"[ORCH-{self.session_id}] resampy unavailable: {e}")
            return
        try:
            audio16 = await asyncio.get_event_loop().run_in_executor(
                None, lambda: resampy.resample(audio, sr_orig=sr_in, sr_new=self.cfg.sample_rate_out)
            )
            audio16 = audio16.astype(np.float32, copy=False)
        except Exception as e:
            logger.warning(f"[ORCH-{self.session_id}] Resample failed: {e}")
            return

        if not self.is_turn_active(turn_id):
            return

        text = None
        if self._asr is None:
            logger.warning(f"[ORCH-{self.session_id}] ASR disabled; skipping")
            return
        try:
            text = await self._asr.recognize(audio16)
        except Exception as e:
            logger.warning(f"[ORCH-{self.session_id}] ASR error: {e}")
            return

        if not self.is_turn_active(turn_id):
            return

        if not text or not str(text).strip():
            return
        text = str(text).strip()

        # Dedup identical transcripts in a short window
        now = time.perf_counter()
        if self._last_asr_text and text == self._last_asr_text and (now - self._last_asr_text_time) * 1000.0 < self.cfg.dedup_window_ms:
            return
        self._last_asr_text = text
        self._last_asr_text_time = now

        logger.info(f"[ORCH-{self.session_id}] ASR: {text}")
        self._send_custom_msg(f"ASR_RESULT:{text}")

        # Kick off LLM streaming (turn-aware wrapper discards cancelled output)
        turn_nerfreal = _TurnAwareNerfreal(self, turn_id)
        try:
            from llm import llm_response
            await asyncio.get_event_loop().run_in_executor(None, llm_response, text, turn_nerfreal, self.avatar_name)
        except Exception as e:
            logger.warning(f"[ORCH-{self.session_id}] LLM error: {e}")
